from flask import Flask, request, send_file, render_template, Response, session
import requests
from pypdf import PdfWriter
import os
import time
import uuid  # Для создания уникального ID сессии

app = Flask(__name__, template_folder="templates")
app.secret_key = "supersecretkey"  # Секретный ключ для сессий

API_KEY = "1996045f-5888-4545-be50-d6fa8c0948c9"  # Замени на свой API-ключ
BASE_URL = "https://cloud.uislab.com/ords/oms_fargo/v1/orders/print"
TEMP_FOLDER = "temp"  # Общая папка для всех сессий
progress = {}  # Словарь для хранения прогресса каждого пользователя

@app.route("/", methods=["GET"])
def index():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())  # Привязываем пользователя к одной сессии
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate_pdf():
    session_id = session.get("session_id")  # Получаем ID сессии пользователя
    session_folder = os.path.join(TEMP_FOLDER, session_id)
    os.makedirs(session_folder, exist_ok=True)  # Создаём папку для пользователя (если нет)
    
    progress[session_id] = 0  # Обнуляем прогресс

    order_ids = request.form.get("order_ids", "").split(",")
    order_ids = [order_id.strip() for order_id in order_ids if order_id.strip()]

    if not order_ids:
        return "Ошибка: введите хотя бы один ID", 400

    pdf_writer = PdfWriter()
    pdf_files = []
    total_orders = len(order_ids)

    for index, order_id in enumerate(order_ids, start=1):
        pdf_url = f"{BASE_URL}?order_id={order_id}&code=barcode&api_key={API_KEY}"
        response = requests.get(pdf_url)

        if response.status_code == 200:
            pdf_path = os.path.join(session_folder, f"{order_id}.pdf")
            with open(pdf_path, "wb") as f:
                f.write(response.content)
            pdf_files.append(pdf_path)
            with open(pdf_path, "rb") as f:
                pdf_writer.append(f)

        progress[session_id] = int((index / total_orders) * 100)
        time.sleep(0.5)  # Имитация задержки для плавности
    
    output_pdf = os.path.join(session_folder, "merged_orders.pdf")
    with open(output_pdf, "wb") as out_f:
        pdf_writer.write(out_f)
    pdf_writer.close()
    
    progress[session_id] = 100  # Завершаем процесс
    time.sleep(1)  # Короткая пауза, чтобы фронт успел обновить 100%
    return session_id  # Возвращаем ID сессии пользователю

@app.route("/progress/<session_id>")
def progress_status(session_id):
    def generate():
        while session_id in progress and progress[session_id] < 100:
            yield f"data:{progress[session_id]}\n\n"
            time.sleep(0.5)
        yield "data:100\n\n"
    return Response(generate(), mimetype="text/event-stream")

@app.route("/download/<session_id>")
def download(session_id):
    session_folder = os.path.join(TEMP_FOLDER, session_id)
    output_pdf = os.path.join(session_folder, "merged_orders.pdf")

    if os.path.exists(output_pdf):
        response = send_file(output_pdf, as_attachment=True)

        # Удаляем файлы и папку после скачивания
        @response.call_on_close
        def cleanup():
            try:
                for file in os.listdir(session_folder):
                    os.remove(os.path.join(session_folder, file))
                time.sleep(1)  # Даем системе время закрыть файлы
                os.rmdir(session_folder)  # Удаляем саму папку
                progress.pop(session_id, None)  # Удаляем прогресс этой сессии
            except Exception as e:
                print(f"Ошибка при удалении файлов: {e}")

        return response
    else:
        return "Файл не найден", 404

if __name__ == "__main__":
    app.run(debug=True)
