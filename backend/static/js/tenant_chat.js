// WaveBook AI Assistant + customer chat widget (shared across tenant pages).
// Reads slug/base from the #assistant-fab data attributes.
(function () {
  const fab = document.getElementById('assistant-fab');
  if (!fab) return;
  const slug = fab.dataset.slug;
  const panel = document.getElementById('assistant-panel');
  const messagesEl = document.getElementById('assistant-messages');
  const assistantInput = document.getElementById('assistant-input');
  const assistantSendBtn = document.getElementById('assistant-send');
  const apiBase = '/t/' + encodeURIComponent(slug) + '/api';
  let greeted = false;
  let chatMode = false;
  let chatToken = null;
  let lastMessageId = 0;
  let chatTimer = null;

  function addBubble(text, who) {
    const el = document.createElement('div');
    el.className = 'assistant-bubble ' + who;
    el.textContent = text;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  function addTyping() {
    const el = document.createElement('div');
    el.className = 'assistant-bubble bot assistant-typing';
    el.textContent = '…';
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  function addPicks(buttons) {
    const row = document.createElement('div');
    row.className = 'assistant-picks';
    buttons.forEach(b => {
      const btn = document.createElement('button');
      btn.className = 'assistant-pick';
      btn.textContent = b.label;
      btn.addEventListener('click', b.onClick);
      row.appendChild(btn);
    });
    messagesEl.appendChild(row);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function openAssistant() {
    panel.classList.add('open');
    if (!greeted) {
      greeted = true;
      addBubble("Hi! I'm the WaveBook AI Assistant. Are you here to book an appointment, or would you like to chat with us?", 'bot');
      addPicks([
        { label: '📅 Book an appointment', onClick: () => assistantSend("I'd like to book an appointment") },
        { label: '💬 Chat with the owner', onClick: showChatStart },
      ]);
    }
    assistantInput.focus();
  }

  function assistantSend(text) {
    text = (text || '').trim();
    if (!text) return;
    addBubble(text, 'user');
    assistantInput.value = '';
    const typing = addTyping();
    fetch(apiBase + '/assistant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    })
      .then(r => r.json())
      .then(data => {
        typing.remove();
        addBubble(data.reply, 'bot');
        if (data.services && data.services.length) {
          addPicks(data.services.map(s => ({
            label: s.name,
            onClick: () => assistantSend("I'd like to book " + s.name)
          })));
        }
        if (data.slots && data.slots.length) {
          addPicks(data.slots.map(slot => ({
            label: slot.display,
            onClick: () => bookSlot(slot, data.service_id)
          })));
        }
      })
      .catch(() => {
        typing.remove();
        addBubble("Sorry, I couldn't process that. Please try again.", 'bot');
      });
  }

  function bookSlot(slot, serviceId) {
    const bookingUrl = base + '/booking?service=' + encodeURIComponent(serviceId) +
      '&date=' + encodeURIComponent(slot.date) + '&time=' + encodeURIComponent(slot.time);
    addBubble("Great — open the booking page to complete your booking. I've preselected the service and time for you.", 'bot');
    addPicks([
      { label: '📅 Open booking page', onClick: () => { window.location.href = bookingUrl; } }
    ]);
    // If we're already on the booking page, fill the form in place too.
    const svc = document.getElementById('service-select');
    const dateInput = document.getElementById('booking-date');
    const timeSelect = document.getElementById('booking-time');
    if (!svc || !dateInput || !timeSelect) return;
    svc.value = String(serviceId);
    svc.dispatchEvent(new Event('change'));
    dateInput.value = slot.date;
    dateInput.dispatchEvent(new Event('input'));
    const timer = setInterval(() => {
      const match = Array.from(timeSelect.options).find(o => o.value === slot.time);
      if (match) {
        clearInterval(timer);
        timeSelect.value = slot.time;
        panel.classList.remove('open');
        const form = document.querySelector('.form-container');
        if (form) form.scrollIntoView({ behavior: 'smooth' });
      } else if (timeSelect.options.length > 1 && timeSelect.options[1].value) {
        clearInterval(timer);
        panel.classList.remove('open');
        const form = document.querySelector('.form-container');
        if (form) form.scrollIntoView({ behavior: 'smooth' });
      }
    }, 150);
    setTimeout(() => clearInterval(timer), 8000);
  }

  // ---- Customer chat ----
  function showChatStart() {
    addBubble("Great — please enter your name and phone number to start chatting. If you've chatted with us in the last 24 hours, use the same phone number to continue.", 'bot');
    const form = document.createElement('div');
    form.className = 'assistant-picks';
    form.style.flexDirection = 'column';
    form.style.alignItems = 'stretch';
    const nameInput = document.createElement('input');
    nameInput.placeholder = 'Your name';
    nameInput.style.cssText = 'border:1px solid #e5d9e0;border-radius:10px;padding:10px 12px;font-size:0.92rem;';
    const phoneInput = document.createElement('input');
    phoneInput.placeholder = 'Phone number';
    phoneInput.type = 'tel';
    phoneInput.style.cssText = nameInput.style.cssText;
    const startBtn = document.createElement('button');
    startBtn.className = 'assistant-pick';
    startBtn.textContent = 'Start chat';
    startBtn.style.cssText = 'border-radius:10px;padding:10px;';
    startBtn.addEventListener('click', () => beginChat(nameInput.value, phoneInput.value));
    form.append(nameInput, phoneInput, startBtn);
    messagesEl.appendChild(form);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    nameInput.focus();
  }

  function beginChat(name, phone) {
    name = (name || '').trim();
    phone = (phone || '').trim();
    if (!name || !phone) {
      addBubble("Please enter both your name and phone number.", 'bot');
      return;
    }
    addBubble(name + ' · ' + phone, 'user');
    const typing = addTyping();
    fetch(apiBase + '/chat/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, phone: phone })
    })
      .then(r => r.json())
      .then(data => {
        typing.remove();
        if (data.detail) {
          addBubble("Sorry, we couldn't start the chat: " + data.detail, 'bot');
          return;
        }
        chatMode = true;
        chatToken = data.token;
        lastMessageId = 0;
        assistantInput.placeholder = 'Type your message...';
        assistantSendBtn.textContent = 'Send';
        addBubble("You're connected! The owner will reply here when they're available.", 'bot');
        (data.messages || []).forEach(m => addBubble(m.body, m.sender === 'customer' ? 'user' : 'bot'));
        lastMessageId = (data.messages || []).length ? data.messages[data.messages.length - 1].id : 0;
        startChatPolling();
      })
      .catch(() => {
        typing.remove();
        addBubble("Sorry, we couldn't start the chat. Please try again.", 'bot');
      });
  }

  function sendChatMessage(text) {
    text = (text || '').trim();
    if (!text || !chatToken) return;
    addBubble(text, 'user');
    assistantInput.value = '';
    fetch(apiBase + '/chat/' + chatToken + '/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body: text })
    })
      .then(r => r.json())
      .then(m => { if (m.id > lastMessageId) lastMessageId = m.id; })
      .catch(() => addBubble("Message failed to send. Please try again.", 'bot'));
  }

  function startChatPolling() {
    if (chatTimer) clearInterval(chatTimer);
    chatTimer = setInterval(() => {
      if (!chatToken) return;
      fetch(apiBase + '/chat/' + chatToken + '/messages?since=' + lastMessageId)
        .then(r => r.json())
        .then(data => {
          (data.messages || []).forEach(m => {
            addBubble(m.body, m.sender === 'customer' ? 'user' : 'bot');
            if (m.id > lastMessageId) lastMessageId = m.id;
          });
        })
        .catch(() => {});
    }, 5000);
  }

  fab.addEventListener('click', openAssistant);
  const closeBtn = document.getElementById('assistant-close');
  if (closeBtn) closeBtn.addEventListener('click', () => {
    panel.classList.remove('open');
    if (chatTimer) clearInterval(chatTimer);
  });
  assistantSendBtn.addEventListener('click', () => {
    if (chatMode) sendChatMessage(assistantInput.value);
    else assistantSend(assistantInput.value);
  });
  assistantInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      if (chatMode) sendChatMessage(assistantInput.value);
      else assistantSend(assistantInput.value);
    }
  });
})();
