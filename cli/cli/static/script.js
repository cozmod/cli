// --- DOM Elements ---
const commandInput = document.getElementById('command-input');
const terminalContainer = document.getElementById('terminal-container');
const outputContainer = document.getElementById('output-container');
const thinkingContainer = document.getElementById('thinking-container');
const toolsContainer = document.getElementById('tools-container');
const startEngineBtn = document.getElementById('start-engine-btn');
const engineStatus = document.getElementById('engine-status');
const sendCommandBtn = document.getElementById('send-command-btn');
const clearTerminalBtn = document.getElementById('clear-terminal-btn');
const tabButtons = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const commandButtons = document.querySelectorAll('.command-btn');

// --- WebSocket Connection ---
const socket = new WebSocket(`ws://${window.location.host}/ws`);

socket.onopen = function(event) {
    console.log("WebSocket connection established.");
    addTerminalLine("ارتباط با بک‌اند برقرار شد. برای شروع، موتور را راه‌اندازی کنید.", 'output');
};

socket.onmessage = function(event) {
    try {
        const data = JSON.parse(event.data);
        handleBackendMessage(data);
    } catch (e) {
        console.error("Error parsing message from backend:", e);
    }
};

socket.onclose = function(event) {
    console.log("WebSocket connection closed.");
    addTerminalLine("ارتباط با بک‌اند قطع شد. لطفاً صفحه را رفرش کنید.", 'output');
    setEngineStatus(false, true); // Set status to stopped on disconnect
};

socket.onerror = function(error) {
    console.error("WebSocket Error:", error);
};

/**
 * Handles messages received from the Python backend.
 */
function handleBackendMessage(data) {
    switch (data.type) {
        case 'terminal':
            addTerminalLine(data.payload.content, data.payload.type);
            break;
        case 'gemini_output':
            appendToOutputPanel(data.payload.content);
            // فعال کردن تب خروجی
            activateTab('output');
            break;
        case 'thinking_output':
            appendToThinkingPanel(data.payload.content);
            break;
        case 'tool_output':
            appendToToolsPanel(data.payload.content);
            break;
        case 'command_type':
            handleCommandType(data.payload.type, data.payload.command);
            break;
        case 'engine_started':
            setEngineStatus(true);
            break;
        case 'engine_stopped':
            setEngineStatus(false, data.payload?.error);
            break;
        default:
            console.warn("Unknown message type from backend:", data.type);
    }
}

/**
 * Sends an action to the Python backend via WebSocket.
 */
function sendActionToBackend(action, payload = {}) {
    if (socket.readyState === WebSocket.OPEN) {
        const message = JSON.stringify({ action, ...payload });
        socket.send(message);
    } else {
        addTerminalLine('خطا: ارتباط با بک‌اند برقرار نیست.', 'output');
    }
}

// --- UI Update Functions ---

function setEngineStatus(isRunning, hasError = false) {
    if (isRunning) {
        engineStatus.textContent = '● موتور: در حال اجرا';
        engineStatus.className = 'status-running';
        startEngineBtn.disabled = true;
        commandInput.disabled = false;
        sendCommandBtn.disabled = false;
        commandInput.placeholder = 'دستور خود را اینجا وارد کنید...';
        commandInput.focus();
        outputContainer.textContent = ''; // Clear initial message
        thinkingContainer.textContent = ''; // Clear thinking container
        toolsContainer.textContent = ''; // Clear tools container
    } else {
        engineStatus.textContent = '● موتور: متوقف';
        engineStatus.className = hasError ? 'status-error' : 'status-stopped';
        startEngineBtn.disabled = false;
        commandInput.disabled = true;
        sendCommandBtn.disabled = true;
        commandInput.placeholder = 'ابتدا موتور را راه‌اندازی کنید...';
    }
}

function addTerminalLine(content, type = 'output') {
    const line = document.createElement('div');
    line.classList.add('line');
    
    if (type === 'command') {
        line.innerHTML = `<span class="prompt">$ </span><span class="command">${content}</span>`;
    } else {
        line.innerHTML = `<span class="output">${content}</span>`;
    }
    
    terminalContainer.appendChild(line);
    terminalContainer.scrollTop = terminalContainer.scrollHeight;
}

function appendToOutputPanel(text) {
    // Appends text to the main output panel, preserving line breaks
    outputContainer.textContent += text;
    outputContainer.parentElement.scrollTop = outputContainer.parentElement.scrollHeight;
}

function appendToThinkingPanel(text) {
    // Appends text to the thinking panel
    thinkingContainer.textContent = text; // Replace content instead of appending
    thinkingContainer.parentElement.scrollTop = thinkingContainer.parentElement.scrollHeight;
    
    // فعال کردن تب تفکر اگر محتوا داشته باشد
    if (text.trim() !== '') {
        // تغییر رنگ دکمه تب برای نشان دادن محتوای جدید
        const thinkingTab = document.querySelector('.tab-btn[data-tab="thinking"]');
        thinkingTab.style.color = 'var(--accent-color)';
    }
}

function appendToToolsPanel(text) {
    // Appends text to the tools panel
    const toolEntry = document.createElement('div');
    toolEntry.classList.add('tool-entry');
    toolEntry.textContent = text;
    
    // اضافه کردن به ابتدای لیست
    if (toolsContainer.firstChild) {
        toolsContainer.insertBefore(toolEntry, toolsContainer.firstChild);
    } else {
        toolsContainer.appendChild(toolEntry);
    }
    
    toolsContainer.parentElement.scrollTop = 0; // اسکرول به بالا
    
    // فعال کردن تب ابزارها اگر محتوا داشته باشد
    const toolsTab = document.querySelector('.tab-btn[data-tab="tools"]');
    toolsTab.style.color = 'var(--accent-color)';
}

function activateTab(tabName) {
    // غیرفعال کردن همه تب‌ها
    tabButtons.forEach(btn => btn.classList.remove('active'));
    tabContents.forEach(content => content.classList.remove('active'));
    
    // فعال کردن تب مورد نظر
    const activeTabBtn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    const activeTabContent = document.getElementById(`${tabName}-tab`);
    
    if (activeTabBtn && activeTabContent) {
        activeTabBtn.classList.add('active');
        activeTabContent.classList.add('active');
        
        // بازنشانی رنگ دکمه تب
        activeTabBtn.style.color = '';
    }
}

function handleCommandType(type, command) {
    // اضافه کردن کلاس خاص به دستور در ترمینال
    const commandLines = document.querySelectorAll('.terminal-view .line .command');
    if (commandLines.length > 0) {
        const lastCommandLine = commandLines[commandLines.length - 1];
        lastCommandLine.classList.add(`command-${type}`);
    }
}

// --- Event Listeners ---

startEngineBtn.addEventListener('click', () => {
    startEngineBtn.disabled = true;
    engineStatus.textContent = '● موتور: در حال راه‌اندازی...';
    engineStatus.className = 'status-starting';
    sendActionToBackend('start_engine');
});

commandInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.value.trim() !== '') {
        const command = e.target.value.trim();
        sendActionToBackend('send_command', { command: command });
        e.target.value = '';
    }
});

sendCommandBtn.addEventListener('click', () => {
    if (commandInput.value.trim() !== '') {
        const command = commandInput.value.trim();
        sendActionToBackend('send_command', { command: command });
        commandInput.value = '';
        commandInput.focus();
    }
});

// رویداد برای دکمه‌های دستور
commandButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        if (!commandInput.disabled) {
            const prefix = btn.getAttribute('data-prefix');
            commandInput.value = prefix + ' ';
            commandInput.focus();
        }
    });
});

// رویداد برای تب‌ها
tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        const tabName = btn.getAttribute('data-tab');
        activateTab(tabName);
    });
});

// رویداد برای پاک کردن ترمینال
clearTerminalBtn.addEventListener('click', () => {
    terminalContainer.innerHTML = '';
    addTerminalLine('ترمینال پاک شد.', 'output');
});