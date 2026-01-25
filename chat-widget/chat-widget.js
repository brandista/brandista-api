/**
 * BRANDISTA CHAT WIDGET V2 - WITH DEMO MODE
 * GPT-powered chat with ultra-modern UI
 * Includes demo mode for testing without backend
 */

class BrandistaChat {
    constructor(config = {}) {
        // Configuration
        this.config = {
            apiUrl: config.apiUrl || 'http://localhost:8000',
            agentId: config.agentId || 'brandista-chat',
            demoMode: config.demoMode !== undefined ? config.demoMode : true, // Enable demo by default
            ...config
        };

        // DOM elements
        this.toggleBtn = document.getElementById('chat-toggle-btn');
        this.chatWindow = document.getElementById('chat-window');
        this.closeBtn = document.getElementById('chat-close-btn');
        this.messagesContainer = document.getElementById('chat-messages');
        this.input = document.getElementById('chat-input');
        this.sendBtn = document.getElementById('chat-send-btn');
        this.typingIndicator = document.getElementById('typing-indicator');

        // State
        this.isOpen = false;
        this.messageHistory = [];
        this.isProcessing = false;

        this.init();
    }

    init() {
        // Event listeners
        this.toggleBtn?.addEventListener('click', () => this.toggleChat());
        this.closeBtn?.addEventListener('click', () => this.closeChat());
        this.sendBtn?.addEventListener('click', () => this.sendMessage());
        this.input?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Quick action buttons
        document.querySelectorAll('.quick-action-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const message = e.target.dataset.message;
                if (message) {
                    this.sendMessage(message);
                }
            });
        });

        // Auto-focus input when opened
        this.chatWindow?.addEventListener('transitionend', () => {
            if (this.isOpen) {
                this.input?.focus();
            }
        });

        // Connect WebSocket if not in demo mode
        if (!this.config.demoMode) {
            this.connectWebSocket();
        } else {
            console.log('🎭 Demo mode enabled - using simulated GPT responses');
        }
    }

    connectWebSocket() {
        try {
            // Convert HTTP URL to WebSocket URL
            const wsUrl = this.config.apiUrl.replace('https://', 'wss://').replace('http://', 'ws://');
            this.ws = new WebSocket(`${wsUrl}/ws/chat`);

            this.ws.onopen = () => {
                console.log('✅ WebSocket connected');
                this.wsConnected = true;
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    if (data.type === 'message') {
                        this.hideTyping();
                        this.addMessage(data.content, 'agent');
                    } else if (data.type === 'typing') {
                        this.showTyping();
                    } else if (data.type === 'error') {
                        this.hideTyping();
                        this.addMessage(data.message || 'Virhe tapahtui', 'agent');
                    } else if (data.type === 'connected') {
                        console.log('💬 Chat connected:', data.message);
                    }
                } catch (error) {
                    console.error('WebSocket message error:', error);
                }
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.wsConnected = false;
            };

            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.wsConnected = false;
                // Attempt reconnect after 5 seconds
                if (!this.config.demoMode) {
                    setTimeout(() => this.connectWebSocket(), 5000);
                }
            };
        } catch (error) {
            console.error('WebSocket connection error:', error);
            this.wsConnected = false;
        }
    }

    toggleChat() {
        if (this.isOpen) {
            this.closeChat();
        } else {
            this.openChat();
        }
    }

    openChat() {
        this.chatWindow?.classList.remove('hidden');
        this.toggleBtn?.classList.add('hidden');
        this.isOpen = true;
        setTimeout(() => this.input?.focus(), 300);
    }

    closeChat() {
        this.chatWindow?.classList.add('hidden');
        this.toggleBtn?.classList.remove('hidden');
        this.isOpen = false;
    }

    async sendMessage(text = null) {
        const message = text || this.input?.value.trim();

        if (!message || this.isProcessing) return;

        // Clear input
        if (this.input) this.input.value = '';

        // Disable send button
        this.isProcessing = true;
        if (this.sendBtn) this.sendBtn.disabled = true;

        // Add user message to UI
        this.addMessage(message, 'user');

        // Show typing indicator
        this.showTyping();

        try {
            let responseMessage;

            if (this.config.demoMode) {
                // Demo mode - simulated GPT responses
                responseMessage = await this.getDemoResponse(message);
            } else {
                // Real API call
                const response = await fetch(`${this.config.apiUrl}/api/v1/chat/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message: message,
                        history: this.messageHistory,
                        agent_id: this.config.agentId
                    })
                });

                if (!response.ok) {
                    throw new Error(`API error: ${response.status}`);
                }

                const data = await response.json();
                responseMessage = data.message;
            }

            // Hide typing indicator
            this.hideTyping();

            // Add GPT response
            if (responseMessage) {
                this.addMessage(responseMessage, 'agent');

                // Update history
                this.messageHistory.push({
                    role: 'user',
                    content: message,
                    timestamp: new Date().toISOString()
                });
                this.messageHistory.push({
                    role: 'assistant',
                    content: responseMessage,
                    timestamp: new Date().toISOString()
                });

                // Keep only last 20 messages for context
                if (this.messageHistory.length > 20) {
                    this.messageHistory = this.messageHistory.slice(-20);
                }
            }
        } catch (error) {
            console.error('Chat error:', error);
            this.hideTyping();
            this.addMessage(
                'Pahoittelut, en pystynyt käsittelemään viestiäsi. Yritä uudelleen hetken kuluttua. 🙏',
                'agent'
            );
        } finally {
            // Re-enable send button
            this.isProcessing = false;
            if (this.sendBtn) this.sendBtn.disabled = false;
            this.input?.focus();
        }
    }

    async getDemoResponse(message) {
        // Simulate API delay
        await new Promise(resolve => setTimeout(resolve, 1000 + Math.random() * 1000));

        const lowerMessage = message.toLowerCase();

        // Demo responses based on keywords
        if (lowerMessage.includes('brandista') || lowerMessage.includes('mikä') || lowerMessage.includes('kerro')) {
            return `Brandista on tekoälypohjainen kilpailija-analyysityökalu! 🎯

**Pääominaisuudet:**
• Automaattinen kilpailija-analyysi
• Verkkosivujen tekninen auditointi
• SEO-analyysi ja suositukset
• Digitaalinen pisteytys (0-100)
• 90 päivän strateginen suunnitelma

Käytämme 6 erikoistunutta AI-agenttia analysoimaan kilpailijasi ja antamaan sinulle käytännön toimenpiteitä. ✨`;
        }

        if (lowerMessage.includes('kilpaili') || lowerMessage.includes('analyysi')) {
            return `Kilpailija-analyysi toimii näin: 🔍

1. **Scout** löytää kilpailijasi automaattisesti
2. **Analyst** analysoi jokaisen verkkosivun
3. **Guardian** tunnistaa riskit ja uhat
4. **Prospector** löytää mahdollisuudet
5. **Strategist** antaa strategiset suositukset
6. **Planner** luo 90 päivän toimintasuunnitelman

Koko prosessi kestää vain ~90 sekuntia! ⚡`;
        }

        if (lowerMessage.includes('ominaisuus') || lowerMessage.includes('mitä')) {
            return `Brandistan ominaisuudet: ✨

📊 **Analyysit:**
• SEO-analyysi
• Tekninen auditointi
• Sisältöanalyysi
• Mobiiliystävällisyys
• Turvallisuusanalyysi

🎯 **Strategia:**
• SWOT-analyysi
• Kilpailija-vertailu
• Markkina-asemointi
• 90 päivän suunnitelma

🤖 **AI-agentit:**
6 erikoistunutta agenttia työskentelee yhdessä antaakseen sinulle parhaat oivallukset!`;
        }

        if (lowerMessage.includes('hinta') || lowerMessage.includes('maksa')) {
            return `Brandistan hinnoittelu on joustava! 💰

Tarjoamme erilaisia paketteja yrityksesi tarpeisiin. Ota yhteyttä, niin kerromme lisää:

📧 info@brandista.eu
🌐 www.brandista.eu

Voimme myös järjestää ilmaisen demon! 🎯`;
        }

        if (lowerMessage.includes('kiitos') || lowerMessage.includes('hyvä')) {
            return `Ole hyvä! 😊 

Onko jotain muuta, missä voin auttaa? Voin kertoa lisää:
• Kilpailija-analyysistä
• AI-agenteista
• Hinnoittelusta
• Teknisistä ominaisuuksista

Kysy rohkeasti! 💬`;
        }

        // Default response
        return `Hei! 👋 Olen Brandista AI-assistentti.

Voin auttaa sinua:
• Kilpailija-analyysissä
• SEO-optimoinnissa
• Digitaalisen markkinoinnin strategiassa
• Verkkosivujen teknisessä auditoinnissa

Mitä haluaisit tietää? 🤔`;
    }

    addMessage(text, type = 'agent') {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;

        const time = new Date().toLocaleTimeString('fi-FI', {
            hour: '2-digit',
            minute: '2-digit'
        });

        // Convert markdown-style formatting to HTML
        const formattedText = this.formatMessage(text);

        if (type === 'agent') {
            messageDiv.innerHTML = `
                <div class="message-avatar">
                    <img src="https://www.brandista.eu/logo.png" alt="Brandista" 
                         onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2236%22 height=%2236%22%3E%3Cdefs%3E%3ClinearGradient id=%22grad%22 x1=%220%25%22 y1=%220%25%22 x2=%22100%25%22 y2=%22100%25%22%3E%3Cstop offset=%220%25%22 style=%22stop-color:%23667eea;stop-opacity:1%22 /%3E%3Cstop offset=%22100%25%22 style=%22stop-color:%23764ba2;stop-opacity:1%22 /%3E%3C/linearGradient%3E%3C/defs%3E%3Crect fill=%22url(%23grad)%22 width=%2236%22 height=%2236%22 rx=%2218%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22white%22 font-size=%2218%22 font-family=%22sans-serif%22 font-weight=%22bold%22%3EB%3C/text%3E%3C/svg%3E'">
                </div>
                <div class="message-content">
                    <p>${formattedText}</p>
                    <span class="message-time">${time}</span>
                </div>
            `;
        } else {
            messageDiv.innerHTML = `
                <div class="message-content">
                    <p>${this.escapeHtml(text)}</p>
                    <span class="message-time">${time}</span>
                </div>
            `;
        }

        // Insert before typing indicator
        if (this.typingIndicator) {
            this.messagesContainer?.insertBefore(messageDiv, this.typingIndicator);
        } else {
            this.messagesContainer?.appendChild(messageDiv);
        }

        // Scroll to bottom with smooth animation
        this.scrollToBottom();
    }

    formatMessage(text) {
        // Simple markdown-like formatting
        let formatted = this.escapeHtml(text);

        // Bold: **text** or __text__
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/__(.*?)__/g, '<strong>$1</strong>');

        // Italic: *text* or _text_
        formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
        formatted = formatted.replace(/_(.*?)_/g, '<em>$1</em>');

        // Bullet points: •
        formatted = formatted.replace(/•/g, '<span style="color: #667eea;">•</span>');

        // Line breaks
        formatted = formatted.replace(/\n/g, '<br>');

        return formatted;
    }

    showTyping() {
        this.typingIndicator?.classList.remove('hidden');
        this.scrollToBottom();
    }

    hideTyping() {
        this.typingIndicator?.classList.add('hidden');
    }

    scrollToBottom() {
        if (this.messagesContainer) {
            setTimeout(() => {
                this.messagesContainer.scrollTo({
                    top: this.messagesContainer.scrollHeight,
                    behavior: 'smooth'
                });
            }, 100);
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Public API methods
    sendCustomMessage(message) {
        this.sendMessage(message);
    }

    open() {
        this.openChat();
    }

    close() {
        this.closeChat();
    }

    clearHistory() {
        this.messageHistory = [];
    }

    setDemoMode(enabled) {
        this.config.demoMode = enabled;
        console.log(`🎭 Demo mode ${enabled ? 'enabled' : 'disabled'}`);
    }

    destroy() {
        // Remove event listeners
        this.toggleBtn?.removeEventListener('click', this.toggleChat);
        this.closeBtn?.removeEventListener('click', this.closeChat);
        this.sendBtn?.removeEventListener('click', this.sendMessage);
    }
}

// Initialize chat widget when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Initialize with demo mode enabled by default
    window.brandistaChat = new BrandistaChat({
        apiUrl: 'http://localhost:8000',
        agentId: 'brandista-chat-gpt',
        demoMode: true // Set to false when API is running
    });

    // Log initialization
    console.log('🎯 Brandista Chat Widget V2 initialized');
    console.log('🎭 Demo mode: ON (simulated GPT responses)');
    console.log('💡 To use real API: brandistaChat.setDemoMode(false)');
});

// Expose to window for external access
window.BrandistaChat = BrandistaChat;
