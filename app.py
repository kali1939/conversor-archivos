import os
import time
from flask import Flask, request, jsonify, render_template
import requests
from dotenv import load_dotenv

# Cargar API Key
load_dotenv()
CLOUDCONVERT_API_KEY = os.getenv("CLOUDCONVERT_API_KEY")
CLOUDCONVERT_JOBS_URL = "https://api.cloudconvert.com/v2/jobs"

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/convert", methods=["POST"])
def convert_file():
    try:
        files = request.files.getlist("file")
        target_format = request.form.get("target_format")

        if not files or not target_format:
            return jsonify({"error": "Se requiere al menos un archivo y target_format"}), 400

        download_urls = []
        headers = {"Authorization": f"Bearer {CLOUDCONVERT_API_KEY}"}

        for file in files:
            input_path = f"temp_{file.filename}"
            file.save(input_path)

            # 1️⃣ Crear job
            job_data = {
                "tasks": {
                    "import-file": {"operation": "import/upload"},
                    "convert-file": {
                        "operation": "convert",
                        "input": "import-file",
                        "output_format": target_format
                    },
                    "export-file": {"operation": "export/url", "input": "convert-file"}
                }
            }

            job_response = requests.post(CLOUDCONVERT_JOBS_URL, headers=headers, json=job_data)
            job = job_response.json()["data"]

            # 2️⃣ Subir archivo al URL de importación
            import_task = next(t for t in job["tasks"] if t["name"] == "import-file")
            upload_url = import_task["result"]["form"]["url"]
            upload_params = import_task["result"]["form"]["parameters"]

            with open(input_path, "rb") as f:
                files_payload = {"file": f}
                requests.post(upload_url, data=upload_params, files=files_payload)

            # 3️⃣ Polling hasta que la conversión termine
            job_id = job["id"]
            while True:
                job_status_resp = requests.get(f"{CLOUDCONVERT_JOBS_URL}/{job_id}", headers=headers)
                job_status = job_status_resp.json()["data"]
                if job_status["status"] == "finished":
                    break
                elif job_status["status"] == "error":
                    os.remove(input_path)
                    return jsonify({"error": "Error en la conversión"}), 500
                time.sleep(2)  # espera 2 segundos

            # 4️⃣ Obtener URL de descarga
            final_job_resp = requests.get(f"{CLOUDCONVERT_JOBS_URL}/{job_id}", headers=headers).json()["data"]
            export_task = next(t for t in final_job_resp["tasks"] if t["name"] == "export-file")
            file_url = export_task["result"]["files"][0]["url"]
            download_urls.append({"original_filename": file.filename, "download_url": file_url})

            # Borrar archivo temporal
            os.remove(input_path)

        return jsonify({"files": download_urls})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Railway asigna el puerto
    app.run(host="0.0.0.0", port=port, debug=True)
