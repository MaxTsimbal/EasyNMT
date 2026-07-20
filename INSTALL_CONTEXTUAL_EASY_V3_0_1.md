# Install Contextual Easy v3.0.1

This patch is applied over the already installed Task 3C Final project.
It does not contain `.env`, `.git`, `.venv`, user databases, or Railway volume data.

After copying the patch over `EasyNMT_Public`:

```powershell
.\.venv\Scripts\python.exe -m compileall -q .
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:5000`, then hard-refresh with `Ctrl + F5`.

The badge inside the Easy panel is intentionally truthful:

- `Онлайн AI` means OpenAI is configured and the answer came from the model.
- `Офлайн підказка` means no active OpenAI connection was available and a safe local explanation was used.
- `Ліміт AI` means the daily limit was reached.
- `Без готових відповідей` means the active-test guard handled the request.

For Railway, `OPENAI_API_KEY` must exist in the service variables. Never paste the key into source files or Git.
