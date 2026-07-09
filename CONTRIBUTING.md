# Contributing

Thank you for your interest in contributing to Nova Voice Assistant.

## How to Contribute

1. Fork the repository.
2. Create a feature branch:

   ```bash
   git checkout -b feat/your-feature-name
   ```

3. Make your changes.
4. Test the app locally.
5. Commit using a clear Conventional Commit message:

   ```bash
   git commit -m "feat: add your feature"
   ```

6. Push your branch:

   ```bash
   git push origin feat/your-feature-name
   ```

7. Open a pull request.

## Commit Message Examples

- `feat: add language selector for speech recognition`
- `fix: improve microphone restart behavior`
- `docs: update installation guide`
- `style: refine sidebar contrast`
- `refactor: simplify history rendering`
- `test: add backend route tests`

## Local Development

```bash
python -m venv .venv
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000/` in Chrome or Edge.

