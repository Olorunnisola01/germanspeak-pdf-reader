# GermanSpeak PDF Reader

A dedicated Windows desktop PDF reader built specifically for effective German (language learning) workflow:

- Open any PDF
- **Simple click & drag to highlight** any German text (accurate word-level selection using PyMuPDF)
- Click one big button: **🔊 Speak German** or **🌐 Translate + Speak English**
- High-quality Microsoft neural "Online Natural" voices via edge-tts (the same excellent voices the browser extension prefers on Edge)
- Translation uses the exact same free Google endpoint as the original extension

This completely bypasses the limitations of Edge's built-in PDF viewer (isolated PDF.js text layer).

## How to use (after building the .exe)

1. Run `GermanSpeak-PDF-Reader.exe`
2. Open a PDF (button or drag & drop)
3. Click and drag over German text on the page image → words are highlighted in indigo
4. Click the big purple **🔊 Speak German** button (or the green Translate + Speak button)
5. Enjoy clear neural TTS + see the English translation on the right panel

You can also click the text boxes on the right to replay.

## Building the .exe yourself (from source)

```powershell
cd "GermanSpeak-PDF-Reader"
.\.venv\Scripts\Activate.ps1

# One-file, windowed, nice name
pyinstaller --onefile --windowed `
  --name "GermanSpeak-PDF-Reader" `
  --icon "icons/icon48.jpg" `
  --add-data "icons;icons" `
  app.py
```

The finished executable will be in `dist\GermanSpeak-PDF-Reader.exe`.

You can distribute that single file.

## Requirements (if running from source without the .exe)

See `requirements.txt`.

## Notes

- Best audio quality requires an internet connection (edge-tts uses Microsoft cloud neural voices, exactly like the "Online (Natural)" voices praised in the browser extension).
- Local fallback voices via Windows SAPI are possible in future versions.
- Selection is word-based and very accurate thanks to PyMuPDF's text extraction.
- The app reuses the same translation + voice philosophy as the original GermanSpeak browser extension.

Enjoy learning German from real PDFs!
