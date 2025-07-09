import os
import io
import base64
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from optiland import optic, analysis
from optiland.materials import AbbeMaterial
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

app = Flask(__name__)
CORS(app)  # 👈 Enable CORS for all routes

@app.route("/simulate", methods=["POST"])
def simulate():
    data = request.get_json()
    try:
        efl = float(data["efl"])
        f_number = float(data["f_number"])
        hfov = float(data["hfov"])
    except (KeyError, ValueError):
        return jsonify({"error": "Missing or invalid parameters"}), 400

    zmx_path = download_zmx_file(efl, f_number, hfov)
    lens = parse_zmx_and_create_optic(zmx_path)

    img1 = render_plot(lens.draw, 10)
    img2 = render_plot(analysis.Distortion(lens).view)
    img3 = render_plot(analysis.RayFan(lens).view)

    return jsonify({
        "draw": img1,
        "distortion": img2,
        "rayfan": img3
    })

def download_zmx_file(efl, f_number, hfov, output_dir="lensnet_files"):
    base_url = "https://lensnet.herokuapp.com/"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get(base_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "efl")))
        driver.find_element(By.NAME, "efl").send_keys(str(efl))
        driver.find_element(By.NAME, "f_number").send_keys(str(f_number))
        driver.find_element(By.NAME, "hfov").send_keys(str(hfov))
        driver.find_element(By.CSS_SELECTOR, 'input[type="submit"]').click()
        WebDriverWait(driver, 15).until(EC.presence_of_all_elements_located((By.LINK_TEXT, "Zemax file")))

        folder_name = f"{output_dir}/efl_{efl}_fnum_{f_number}_hfov_{hfov}"
        os.makedirs(folder_name, exist_ok=True)

        for link in driver.find_elements(By.TAG_NAME, "a"):
            href = link.get_attribute("href")
            if href.startswith("data:text/plain;base64,") and "Zemax" in link.text:
                data = base64.b64decode(href.split(",", 1)[1])
                zmx_path = os.path.join(folder_name, "design_1.zmx")
                with open(zmx_path, "wb") as f:
                    f.write(data)
                return zmx_path
    finally:
        driver.quit()

def parse_zmx_and_create_optic(zmx_path):
    with open(zmx_path, "r") as f:
        lines = f.readlines()

    lens = optic.Optic()
    aperture_value = 5.0
    wavelengths, yflns = [], []
    index = radius = thickness = n = abbe = None

    for line in lines:
        line = line.strip()
        if line.startswith("ENPD"): aperture_value = float(line.split()[1])
        elif line.startswith("WAVL"): wavelengths = list(map(float, line.split()[1:]))
        elif line.startswith("YFLN"): yflns = list(map(float, line.split()[1:]))
        elif line.startswith("SURF"):
            if index is not None and radius is not None and thickness is not None:
                if n and abbe:
                    lens.add_surface(index=index, radius=radius, thickness=thickness,
                                     material=AbbeMaterial(n=n, abbe=abbe), is_stop=(index == 1))
                else:
                    lens.add_surface(index=index, radius=radius, thickness=thickness, is_stop=(index == 1))
            index = int(line.split()[1])
            radius = thickness = n = abbe = None
        elif line.startswith("CURV"):
            curv = float(line.split()[1])
            radius = np.inf if curv == 0 else 1.0 / curv
        elif line.startswith("DISZ"):
            val = line.split()[1]
            thickness = np.inf if val == "INFINITY" else float(val)
        elif line.startswith("GLAS"):
            parts = line.split()
            n = float(parts[4])
            abbe = float(parts[5])

    if index is not None and radius is not None and thickness is not None:
        if n and abbe:
            lens.add_surface(index=index, radius=radius, thickness=thickness,
                             material=AbbeMaterial(n=n, abbe=abbe), is_stop=(index == 1))
        else:
            lens.add_surface(index=index, radius=radius, thickness=thickness, is_stop=(index == 1))

    lens.add_surface(index=index + 1)
    lens.set_aperture(aperture_type="EPD", value=aperture_value)
    lens.set_field_type("angle")

    for y in (yflns or [0]): lens.add_field(y=y)
    for i, w in enumerate(wavelengths): lens.add_wavelength(value=w, is_primary=(i == 1))

    return lens

def render_plot(plot_func, *args):
    fig = plt.figure()
    plot_func(*args)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=300)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
