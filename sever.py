<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Симулятор холодных звонков</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/RecordRTC/5.6.2/RecordRTC.min.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background-color: var(--tg-theme-bg-color, #ffffff);
            color: var(--tg-theme-text-color, #000000);
        }
        #phone {
            width: 300px;
            height: 600px;
            border: 2px solid var(--tg-theme-button-color, #3390ec);
            border-radius: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: space-between;
            padding: 20px;
            background-color: var(--tg-theme-secondary-bg-color, #f0f0f0);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        #display {
            width: 100%;
            height: 400px;
            background-color: var(--tg-theme-bg-color, #ffffff);
            border: 1px solid var(--tg-theme-hint-color, #999999);
            overflow-y: auto;
            padding: 10px;
            margin-bottom: 20px;
            font-size: 14px;
            line-height: 1.5;
        }
        #display p {
            margin: 5px 0;
            padding: 5px;
            border-radius: 5px;
            max-width: 80%;
        }
        #display p.system {
            background-color: var(--tg-theme-secondary-bg-color, #e6e6e6);
            align-self: center;
            text-align: center;
            font-style: italic;
        }
        #display p.response {
            background-color: var(--tg-theme-button-color, #3390ec);
            color: var(--tg-theme-button-text-color, #ffffff);
            align-self: flex-start;
        }
        #display p.user {
            background-color: var(--tg-theme-secondary-bg-color, #e6e6e6);
            align-self: flex-end;
            text-align: right;
        }
        #display p.error {
            background-color: #ff4d4d;
            color: white;
            align-self: center;
            text-align: center;
        }
        button {
            padding: 10px 20px;
            font-size: 16px;
            background-color: var(--tg-theme-button-color, #3390ec);
            color: var(--tg-theme-button-text-color, #ffffff);
            border: none;
            border-radius: 5px;
            cursor: pointer;
            transition: background-color 0.3s;
        }
        button:hover {
            background-color: var(--tg-theme-secondary-bg-color, #2980b9);
        }
    </style>
</head>
<body>
    <div id="phone">
        <div id="display"></div>
        <button id="callButton">Начать звонок</button>
    </div>

    <script>
        function initApp() {
            let tg = window.Telegram.WebApp;
            let callButton = document.getElementById('callButton');
            let display = document.getElementById('display');
            let isCallActive = false;
            let isTelegramWebApp = tg.initDataUnsafe.query_id !== undefined;
            let recorder;
            let audioBlob;

            console.log('Is Telegram WebApp:', isTelegramWebApp);
            logMessage('App initialized. Is Telegram WebApp: ' + isTelegramWebApp);

            tg.expand();

            callButton.addEventListener('click', toggleCall);

            function toggleCall() {
                if (isCallActive) {
                    endCall();
                } else {
                    startCall();
                }
            }

            async function startCall() {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    recorder = RecordRTC(stream, {
                        type: 'audio',
                        mimeType: 'audio/wav',
                        recorderType: RecordRTC.StereoAudioRecorder
                    });
                    
                    recorder.startRecording();
                    isCallActive = true;
                    callButton.textContent = 'Завершить звонок';
                    addMessage('Звонок начат. Говорите...', 'system');
                    logMessage('Call started');
                    if (isTelegramWebApp) {
                        tg.sendData(JSON.stringify({action: 'startCall'}));
                    }
                } catch (err) {
                    console.error('Error accessing microphone:', err);
                    addMessage('Ошибка доступа к микрофону', 'error');
                }
            }

            function endCall() {
                if (recorder) {
                    recorder.stopRecording(() => {
                        audioBlob = recorder.getBlob();
                        sendAudioToServer(audioBlob);
                    });
                }
                isCallActive = false;
                callButton.textContent = 'Начать звонок';
                addMessage('Звонок завершен', 'system');
                logMessage('Call ended');
                if (isTelegramWebApp) {
                    tg.sendData(JSON.stringify({action: 'endCall'}));
                }
            }

            async function sendAudioToServer(audioBlob) {
                const formData = new FormData();
                formData.append('audio', audioBlob, 'audio.wav');
            
                try {
                    const response = await fetch('http://localhost:5000/recognize_speech', {
                        method: 'POST',
                        body: formData
                    });
            
                    if (response.ok) {
                        const data = await response.json();
                        console.log("User speech:", data.user_speech);
                        console.log("Bot response:", data.bot_response);
                        
                        addMessage(data.user_speech, 'user');
                        addMessage(data.bot_response, 'response');
                        
                        if (data.audio_data) {
                            // Предполагаем, что audio_data - это URL или base64-encoded строка
                            const audio = new Audio(data.audio_data);
                            audio.oncanplaythrough = () => {
                                audio.play().catch(error => console.error("Error playing audio:", error));
                            };
                            audio.onerror = (e) => {
                                console.error("Error loading audio:", e);
                            };
                        }
                    } else {
                        console.error('Server error:', response.statusText);
                        addMessage("Sorry, there was an error processing your request.", 'error');
                    }
                } catch (error) {
                    console.error('Error:', error);
                    addMessage("Sorry, there was an error sending your audio.", 'error');
                }
            
                // Очищаем сообщение о записи
                const recordingStatus = document.getElementById('recordingStatus');
                if (recordingStatus) {
                    recordingStatus.textContent = '';
                }
            }
            
            
            function addMessage(message, type) {
                let p = document.createElement('p');
                p.textContent = type === 'response' ? 'Собеседник: ' + message : 
                                type === 'user' ? 'Вы: ' + message : message;
                p.className = type;
                display.appendChild(p);
                display.scrollTop = display.scrollHeight;
            }

            function logMessage(message) {
                console.log(message);
                if (isTelegramWebApp) {
                    tg.sendData(JSON.stringify({action: 'log', message: message}));
                }
            }

            tg.ready();
        }

        initApp();
    </script>
</body>
</html>
