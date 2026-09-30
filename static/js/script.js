// ---------------- OPTION CLICK & ANSWER CHECK ----------------

document.querySelectorAll('.option-btn').forEach(btn => {
    btn.addEventListener('click', function () {
        const selected = this.getAttribute('data-option');
        document.querySelectorAll('.option-btn').forEach(b => b.disabled = true);

        fetch('/check-answer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'selected_option=' + selected
        })
        .then(res => res.json())
        .then(data => {
            const feedbackEl = document.getElementById('feedbackText');
            feedbackEl.innerText = data.feedback;
            feedbackEl.className = data.is_correct ? 'feedback correct' : 'feedback wrong';

            document.getElementById('nextBtn').style.display = 'inline-block';
            document.getElementById('nextBtn').onclick = function () {
                window.location.href = data.next_url;
            };

            autoLabiExplain();
        });
    });
});

// ---------------- LABI CHAT ----------------

const chatInput = document.getElementById('chatInput');
const chatSendBtn = document.getElementById('chatSendBtn');
const chatMessages = document.getElementById('chatMessages');

if (chatSendBtn) {
    chatSendBtn.addEventListener('click', sendChatMessage);
    chatInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') sendChatMessage();
    });
}

function sendChatMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    appendMessage('You', message);
    chatInput.value = '';

    fetch('/labi-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'message=' + encodeURIComponent(message)
    })
    .then(res => res.json())
    .then(data => {
        appendMessage('LABI', data.reply);
    });
}

function autoLabiExplain() {
    if (!chatMessages) return;
    fetch('/labi-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'message=' + encodeURIComponent('explain')
    })
    .then(res => res.json())
    .then(data => {
        appendMessage('LABI', data.reply);
    });
}

function appendMessage(sender, text) {
    const msgEl = document.createElement('div');
    msgEl.className = sender === 'You' ? 'chat-msg user-msg' : 'chat-msg labi-msg';
    msgEl.innerHTML = `<strong>${sender}:</strong> ${text}`;
    chatMessages.appendChild(msgEl);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}