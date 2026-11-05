# Sintonía

Mi tele de YouTube sin algoritmo. Los canales se definen en `CHANNELS`, al principio del script de `index.html`.
`scripts/update.py` refresca `data.json` cada día mediante GitHub Actions.

Los canales se editan desde Ajustes en la app, que guarda `canales.json`. Al cambiar ese archivo, GitHub Actions regenera `data.json`.
