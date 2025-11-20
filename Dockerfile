# 1. Берем легкую версию Python 3.11
FROM python:3.11-slim

# 2. Отключаем кэширование (чтобы логи были видны сразу)
ENV PYTHONUNBUFFERED=1

# 3. Создаем рабочую папку внутри контейнера
WORKDIR /app

# 4. Копируем файл зависимостей
COPY requirements.txt .

# 5. Устанавливаем библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# 6. Копируем весь остальной код
COPY . .

# 7. Команда запуска 
CMD ["python", "app.py"]