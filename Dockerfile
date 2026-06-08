FROM mcr.microsoft.com/playwright/python:v1.43.0-jammy

WORKDIR /app

# L-image dyal Playwright aslan fiha user 3ndo ID 1000 (smito pwuser)
# Makaynch lach n-siybo wa7ed jdid, ghir n-st3mlouh!

COPY --chown=1000:1000 requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=1000:1000 . .

# Run as UID 1000 (Hugging Face standard)
USER 1000

CMD ["python", "Netflix_TV_Bot.py"]
