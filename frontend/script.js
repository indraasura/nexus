const API_URL = "http://127.0.0.1:8000"; // Local FastAPI address

// Handle file selection display
document.getElementById('file-upload').addEventListener('change', function (e) {
    const fileList = document.getElementById('file-list');
    fileList.innerHTML = Array.from(e.target.files).map(f => `<div>📄 ${f.name}</div>`).join('');
});

async function syncData() {
    const files = document.getElementById('file-upload').files;
    const model = document.getElementById('model-select').value;
    const statusDiv = document.getElementById('sync-status');
    const syncBtn = document.getElementById('sync-btn');

    if (files.length === 0) {
        statusDiv.innerHTML = "⚠️ Select files first.";
        return;
    }

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append("files", files[i]);
    }
    formData.append("model", model);

    syncBtn.disabled = true;
    syncBtn.innerText = "Syncing...";
    statusDiv.innerHTML = "";

    try {
        const response = await fetch(`${API_URL}/upload`, {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        if (response.ok) {
            statusDiv.innerHTML = `✅ ${result.message}`;
        } else {
            statusDiv.innerHTML = `❌ Error: ${result.detail}`;
        }
    } catch (error) {
        statusDiv.innerHTML = "❌ Failed to connect to server.";
    } finally {
        syncBtn.disabled = false;
        syncBtn.innerText = "Sync Data to AI";
    }
}

function handleKeyPress(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
}

function appendMessage(role, text) {
    const container = document.getElementById('chat-container');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    // Parse markdown-style line breaks simply for the frontend
    const formattedText = text.replace(/\n/g, '<br>');

    msgDiv.innerHTML = `<div class="bubble">${formattedText}</div>`;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

async function sendMessage() {
    const input = document.getElementById('user-input');
    const message = input.value.trim();
    const model = document.getElementById('model-select').value;
    const sendBtn = document.getElementById('send-btn');

    if (!message) return;

    appendMessage('user', message);
    input.value = '';
    sendBtn.disabled = true;

    // Add a loading message
    const container = document.getElementById('chat-container');
    const loadingDiv = document.createElement('div');
    loadingDiv.className = `message ai loading`;
    loadingDiv.innerHTML = `<div class="bubble">Thinking...</div>`;
    container.appendChild(loadingDiv);
    container.scrollTop = container.scrollHeight;

    const formData = new FormData();
    formData.append("message", message);
    formData.append("model", model);

    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        container.removeChild(loadingDiv); // Remove loading

        if (response.ok) {
            appendMessage('ai', result.answer);
        } else {
            appendMessage('ai', `⚠️ Error: ${result.detail}`);
        }
    } catch (error) {
        container.removeChild(loadingDiv);
        appendMessage('ai', "❌ Failed to connect to backend server. Is FastAPI running?");
    } finally {
        sendBtn.disabled = false;
    }
}