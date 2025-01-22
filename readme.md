Убедитесь, что виртуальное окружение активировано
Если ваше окружение уже активно, вы должны видеть что-то вроде (venv) перед приглашением терминала. Если нет, активируйте его:

bash
Копировать
Редактировать
source .venv/bin/activate
Установите библиотеку requests
Установите библиотеку с помощью pip:

bash
Копировать
Редактировать
pip install requests
Проверьте установленные библиотеки
Убедитесь, что requests установлена:

bash
pip list
Запустите бота снова
После установки библиотеки повторно запустите ваш скрипт:

bash
python3 bot.py
Если вы планируете добавлять больше зависимостей, рекомендуется создать файл requirements.txt для их отслеживания. Вы можете сделать это так:

bash
pip freeze > requirements.txt
И в будущем устанавливать все зависимости одной командой:

bash
pip install -r requirements.txt