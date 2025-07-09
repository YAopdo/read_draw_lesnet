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

# --- keep the rest of your functions unchanged ---
# download_zmx_file
# parse_zmx_and_create_optic
# render_plot

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
