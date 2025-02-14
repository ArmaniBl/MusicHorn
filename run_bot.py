import subprocess
import time
import sys
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="bot_runner.log"
)
logger = logging.getLogger(__name__)

def run_bot():
    while True:
        try:
            logger.info("Starting bot...")
            # Запускаем main.py как отдельный процесс
            process = subprocess.Popen([sys.executable, "main.py"])
            
            # Ждем завершения процесса
            process.wait()
            
            # Если процесс завершился, логируем это
            exit_code = process.returncode
            logger.warning(f"Bot process ended with exit code: {exit_code}")
            
            # Ждем 5 секунд перед перезапуском
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"Error in runner: {e}")
            time.sleep(5)

if __name__ == "__main__":
    print("Bot runner started!")
    run_bot() 