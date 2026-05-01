## UI Changes Must Be Visible After Edit

After any UI change (templates, static CSS, routes), the server **must** be restarted immediately for the user to verify the result.

```bash
# Restart gunicorn
kill -HUP $(cat /srv/premises-web/gunicorn.pid 2>/dev/null) 2>/dev/null || \
  systemctl restart premises-web 2>/dev/null || \
  ps aux | grep 'gunicorn.*premises-web' | grep -v grep | awk '{print $2}' | head -1 | xargs -r kill -HUP
```

If no gunicorn PID is available, restart the app via systemd or supervisor. Always confirm with a browser refresh afterward.

## OCR (Auto-fill Property Card from Document)

The app supports automatic extraction of property fields from PDF, DOCX, and image files.

- **Endpoint**: `POST /properties/ocr` (returns JSON)
- **Backend**: `app/ocr.py` — uses Tesseract OCR (rus+eng), PyMuPDF, python-docx
- **Fields extracted**: name, type, address, area, floor, cadastralNumber
- **UI**: In the property form (create/edit), there is a "Заполнить из документа" section where users upload a file and click "Распознать"; fields auto-fill after recognition.

### System dependencies
```bash
apt-get install tesseract-ocr tesseract-ocr-rus
```

### Python dependencies
Already in `requirements.txt`: `pytesseract`, `PyMuPDF`, `python-docx`

## Nested Forms Bug

The property edit form (`templates/property_form.html`) previously had nested `<form>` tags (photo/document delete forms inside the main form). Nested forms are invalid HTML and cause the browser to auto-close the outer form, breaking the **Save** button.

**Fix**: Replace nested delete forms with `<button>` elements that trigger `fetch()` POSTs via `data-delete-url` attributes. The JS handler is in the same script block as the OCR code.

Always check for nested forms when adding delete buttons inside multi-part forms.
