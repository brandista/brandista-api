# Brandista Chat Widget

Modern, dependency-free chat widget that integrates with Brandista API.

## Features

✅ **Zero Dependencies** - Pure HTML, CSS, and JavaScript  
✅ **Responsive Design** - Works on desktop and mobile  
✅ **Smooth Animations** - Modern UI with CSS transitions  
✅ **API Integration** - Connects to Brandista API  
✅ **WebSocket Support** - Real-time messaging (optional)  
✅ **Quick Actions** - Pre-defined message buttons  
✅ **Typing Indicator** - Shows when agent is responding  
✅ **Message History** - Maintains conversation context  

## Installation

### Option 1: Standalone Widget

1. Copy the `chat-widget/` folder to your project
2. Include in your HTML:

```html
<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="path/to/chat-widget/chat-widget.css">
</head>
<body>
    <!-- Your content -->
    
    <!-- Chat Widget -->
    <div id="brandista-chat-widget">
        <!-- Widget content from index.html -->
    </div>
    
    <script src="path/to/chat-widget/chat-widget.js"></script>
</body>
</html>
```

### Option 2: Embed via Script

Add this to your website:

```html
<script>
    (function() {
        var script = document.createElement('script');
        script.src = 'https://your-domain.com/chat-widget/chat-widget.js';
        script.async = true;
        document.head.appendChild(script);
        
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'https://your-domain.com/chat-widget/chat-widget.css';
        document.head.appendChild(link);
    })();
</script>
```

## Configuration

Configure the widget by passing options:

```javascript
window.brandistaChat = new BrandistaChat({
    apiUrl: 'https://api.brandista.eu',
    wsUrl: 'wss://api.brandista.eu/ws/chat', // Optional WebSocket
    agentId: 'your-agent-id'
});
```

## API Integration

The widget expects your API endpoint to accept:

```json
POST /api/v1/chat
{
    "message": "User message",
    "agent_id": "brandista-chat-agent",
    "history": [
        {"role": "user", "content": "...", "timestamp": "..."},
        {"role": "agent", "content": "...", "timestamp": "..."}
    ]
}
```

And return:

```json
{
    "message": "Agent response",
    "timestamp": "2026-01-25T14:45:00Z"
}
```

## WebSocket (Optional)

For real-time messaging, the widget supports WebSocket:

```javascript
// Server sends
{
    "type": "message",
    "content": "Agent response"
}

// Or typing indicator
{
    "type": "typing"
}
```

## Customization

### Colors

Edit CSS variables in `chat-widget.css`:

```css
:root {
    --primary-color: #6366f1;
    --primary-hover: #4f46e5;
    /* ... more colors */
}
```

### Logo

Replace the logo URL in HTML:

```html
<img src="https://your-domain.com/your-logo.png" alt="Your Brand">
```

### Quick Actions

Modify quick action buttons in HTML:

```html
<button class="quick-action-btn" data-message="Your custom message">
    🎯 Your Custom Action
</button>
```

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## File Structure

```
chat-widget/
├── index.html          # Widget HTML structure
├── chat-widget.css     # Styles (no dependencies)
├── chat-widget.js      # Logic (vanilla JS)
└── README.md           # This file
```

## Comparison with Old Version

| Feature | Old (Bubble.io) | New (Modern) |
|---------|----------------|--------------|
| Dependencies | jQuery, Bootstrap, Bubble CDN | None ✅ |
| File Size | ~500KB | ~20KB ✅ |
| Customization | Limited | Full control ✅ |
| Performance | Slow (external CDN) | Fast (local) ✅ |
| Security | No integrity checks | XSS protected ✅ |
| Maintenance | Bubble-dependent | Self-hosted ✅ |

## License

Part of the Brandista API project.
