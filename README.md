# turing-display-controller

Controlador Python multiplataforma para pantallas **Turing Smart Display 3.5"**
conectadas por USB-Serial.

## Características

- Tres modos de visualización: **slideshow** (galería), **spotify** (now-playing)
  y **mix** (fotos + frases).
- Sistema de **notificaciones push** con cola FIFO e imagen completa temporal.
- Persistencia de **frases** en SQLite con caché en memoria thread-safe.
- Servidor **FastAPI** con REST + WebSocket y dashboard Jinja2 + HTMX.
- Integración con **Spotify** vía Authorization Code with PKCE.
- Hot-reload de imágenes en `images/`.
- Empaquetable con **PyInstaller** como binario único.

## Requisitos

- **Python 3.12+**
- **uv** (gestor de paquetes y entornos): https://github.com/astral-sh/uv
- Pantalla Turing 3.5" conectada por USB (VID `1A86:PID 5722` o similar)
- Windows 10/11, Debian 12+ (incluido Orange Pi con Debian arm64)

---

## Instalación en Windows

### 1. Instalar uv

```powershell
# Opción A: con winget
winget install --id astral-sh.uv

# Opción B: con pip
pip install uv

# Opción C: instalador oficial (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Reinicia la terminal y verifica:

```powershell
uv --version
```

### 2. Instalar el controlador

```powershell
# Clonar el repo
git clone <repo-url>
cd turing-display-controller

# Sincronizar dependencias (crea .venv automaticamente)
uv sync
```

### 3. Instalar el driver USB-Serial (si Windows no detecta la pantalla)

Windows 10/11 incluye el driver CDC ACM por defecto. Si la pantalla no aparece
en **Administrador de dispositivos → Puertos (COM y LTP)**:

1. Descarga el driver CH340/CH341 desde
   [http://www.wch-ic.com/downloads/CH341SER_EXE.html](http://www.wch-ic.com/downloads/CH341SER_EXE.html)
   (la mayoría de las Turing usan este chip).
2. Descomprime y ejecuta `CH341SER.EXE` como administrador.
3. Reconecta la pantalla.
4. Verifica en **Administrador de dispositivos** que aparezca como
   `USB-SERIAL CH340 (COMx)` o `USB Serial Device (COMx)`.

### 4. Configurar el puerto

Edita `config.ini` y ajusta `[display] com_port`:

```ini
[display]
com_port = COM5       # tu puerto real (o AUTO)
brightness = 70
orientation = portrait
reset_on_startup = false
```

Para encontrar tu puerto:

```powershell
# PowerShell
Get-WmiObject Win32_SerialPort | Select-Object Name, DeviceID
```

### 5. Ejecutar

```powershell
uv run python -m turing_display
```

Dashboard disponible en: `http://localhost:8000`

---

## Instalación en Debian / Orange Pi (arm64)

Probado en **Orange Pi 5** con **Debian 12 Bookworm (arm64)**, también
funciona en Raspberry Pi OS, Ubuntu 22.04+ y cualquier Debian reciente.

> **Filosofía:** todos los comandos usan `sudo`. **No** se ejecuta nada
> desde un venv (causa conflictos con systemd: el venv cambia de path,
> rompe los servicios al actualizar, etc.). El binario compilado con
> PyInstaller es autosuficiente.

### 1. Instalar dependencias de compilación (solo para construir el binario)

Esto se hace **una vez en una máquina de build** (PC de escritorio,
Orange Pi, etc.). En SBCs ARM como Orange Pi se compila directamente
en la placa (2–4 min).

```bash
sudo apt update
sudo apt install -y git build-essential libusb-1.0-0-dev libudev-dev pkg-config
```

### 2. Clonar el repo y compilar el binario

```bash
sudo mkdir -p /opt/turing-build
sudo chown $USER:$USER /opt/turing-build
cd /opt/turing-build
git clone <repo-url> turing-display-controller
cd turing-display-controller

# uv solo lo necesita el proceso de build (no el servicio final)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv sync
uv run python scripts/build.py

# Salida: dist/turing-display-controller/turing-display-controller
```

### 3. Instalar el binario en su ubicación final

```bash
sudo mkdir -p /opt/turing-display-controller
sudo cp -r dist/turing-display-controller/* /opt/turing-display-controller/
sudo chmod +x /opt/turing-display-controller/turing-display-controller
sudo chown -R root:root /opt/turing-display-controller
```

### 4. Crear usuario de servicio

```bash
sudo useradd --system --shell /usr/sbin/nologin \
    --home /opt/turing-display-controller turing
```

### 5. Configurar permisos USB-Serial

Las pantallas Turing usan chip CH340/CH341 (CDC ACM). El servicio
corre como root (ver paso 7), por lo que **no hace falta** agregar
ningún usuario al grupo `dialout`, pero la regla udev sigue siendo
útil para desarrollo local:

```bash
sudo tee /etc/udev/rules.d/99-turing-display.rules >/dev/null <<'EOF'
# Turing Smart Display 3.5" (CH340/CH341 / clones 7522 / 5722)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7522", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5722", MODE="0666"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
```

Verificar:

```bash
# Antes de conectar la pantalla
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null

# Conectar la pantalla y volver a listar
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
# El nuevo dispositivo es tu puerto (típicamente /dev/ttyUSB0)
```

### 6. Configurar `config.ini`

```bash
sudo mkdir -p /etc/turing-display
sudo cp config.ini /etc/turing-display/config.ini
sudo chmod 644 /etc/turing-display/config.ini
sudo chown root:turing /etc/turing-display/config.ini

sudoedit /etc/turing-display/config.ini
```

```ini
[display]
com_port = /dev/ttyUSB0
brightness = 70
orientation = portrait
reset_on_startup = false
```

### 7. Instalar y arrancar el servicio systemd

```bash
sudo tee /etc/systemd/system/turing-display.service >/dev/null <<'EOF'
[Unit]
Description=Turing Smart Display Controller
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/turing-display-controller
ExecStart=/opt/turing-display-controller/turing-display-controller
Environment=TD_CONFIG=/etc/turing-display/config.ini
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now turing-display.service
sudo systemctl status turing-display.service

# Logs en tiempo real
sudo journalctl -u turing-display.service -f
```

Dashboard: `http://<ip-de-tu-orange-pi>:8000`

### Actualizar el binario

```bash
cd /opt/turing-build/turing-display-controller
sudo systemctl stop turing-display.service
git pull
uv sync
uv run python scripts/build.py
sudo cp -r dist/turing-display-controller/* /opt/turing-display-controller/
sudo systemctl start turing-display.service
sudo systemctl status turing-display.service
```

### Desinstalar

```bash
sudo systemctl disable --now turing-display.service
sudo rm /etc/systemd/system/turing-display.service
sudo rm -rf /opt/turing-display-controller
sudo rm -rf /etc/turing-display
sudo rm /etc/udev/rules.d/99-turing-display.rules
sudo userdel turing
sudo systemctl daemon-reload
```

### Reinstalación (desde cero)

Hay dos scripts en `scripts/` que automatizan todo:

```bash
# 1. Limpiar instalación previa (si existe)
sudo bash scripts/clean_pi.sh

# 2. Instalar desde el repo (clonar primero si no lo tenias)
git clone <repo-url>
cd turing-display-controller
sudo bash scripts/install_pi.sh
```

`install_pi.sh` hace todo: instala apt deps, uv, compila el binario
con PyInstaller, lo deploya en `/opt/turing-display-controller/`,
crea el usuario `turing`, regla udev, `config.ini`, unidad systemd
y arranca el servicio.

`clean_pi.sh` borra todo lo anterior: servicio, binarios,
configuración, usuario, regla udev. **No** borra `phrases.db` ni
tokens de Spotify (están en `/var/lib/turing-display/` si usaste el
`config.ini` por defecto; bórralos a mano si quieres).

### Instalación manual paso a paso

Si prefieres hacerlo a mano, sigue la sección
[**Instalación en Debian / Orange Pi (arm64)**](#instalación-en-debian--orange-pi-arm64)
desde el paso 1.

---

## Configuración de Spotify (opcional)

Si quieres usar el modo Spotify necesitas una app en Spotify Developer:

1. Ve a https://developer.spotify.com/dashboard y crea una app.
2. En **Edit Settings → Redirect URIs** agrega EXACTAMENTE:

   ```
   http://127.0.0.1:8000/api/spotify/callback
   ```

   (o `http://<tu-ip>:8000/api/spotify/callback` si accedes desde otro equipo)
3. Copia el **Client ID** y ponlo en `config.ini`:

   ```ini
   [spotify]
   client_id = tu_client_id_aqui
   redirect_uri = http://127.0.0.1:8000/api/spotify/callback
   ```
4. Reinicia la app y abre `http://localhost:8000/api/spotify/auth/start` en tu navegador.
5. Autoriza la app con tu cuenta de Spotify. Los tokens se guardan en
   `./data/spotify_tokens.db` y se refrescan automáticamente.

**Nota importante**: la API de Spotify **solo reporta lo que se
reproduce en la cuenta que autorizó** la app. Si reproduces desde otra
cuenta o dispositivo, no se mostrará.

---

## Solución de problemas

### La pantalla no se detecta

- **Windows**: verifica en Administrador de dispositivos → Puertos. Si no aparece, instala el driver CH340/CH341.
- **Linux**: ejecuta `dmesg | tail` justo después de conectar la pantalla. Debería decir algo como `ch341-uart converter now attached to ttyUSB0`.
- **Verificar cable**: prueba con otro cable USB (algunos cables son solo de carga, no de datos).

### Error de permisos en Linux

```bash
sudo chmod 666 /dev/ttyUSB0   # temporal
# O solucion permanente: agregar al grupo dialout
sudo usermod -aG dialout $USER
```

### Tests fallan

```bash
uv sync --reinstall   # reinstalar dependencias
uv run pytest -q      # correr tests con verbose
```

### Puerto COM ocupado en Windows

Cierra cualquier otra aplicación que use el puerto (PuTTY, Arduino IDE, etc.).

### Display en blanco

- Verifica el cable USB.
- Sube el brillo en `config.ini` (`brightness = 100`).
- Prueba con `reset_on_startup = true` en `[display]`.

---

## Ejecución

```bash
uv run python -m turing_display
```

Dashboard web disponible en `http://localhost:8000`:

- **`/`**: Dashboard principal con el modo actual, botón para cambiar modo, enviar notificaciones.
- **`/api/notify`**: POST para enviar notificaciones.
- **`/api/mode`**: POST para cambiar modo (`slideshow`, `spotify`, `mix`).
- **`/api/status`**: GET estado del sistema.
- **`/api/spotify/auth/start`**: GET para iniciar autorización con Spotify.

API REST completa documentada en `http://localhost:8000/docs` (FastAPI Swagger).

---

## Tests

```bash
uv run pytest -q
```

## Calidad de código

```bash
uv run ruff format .                     # formatear
uv run ruff check --select I --fix .     # arreglar imports
uv run ty check                          # type check
```

## Estructura del proyecto

```
src/turing_display/
├── display/                # Protocolo Rev A (Turing 3.5")
├── modes/                  # slideshow, spotify, mix
├── notifications/          # Cola FIFO + imagen completa
├── phrases/                # aiosqlite + cache
├── spotify_integration/    # PKCE
├── api/                    # FastAPI + WebSocket
└── web/                    # Templates + estaticos

tests/                      # 141 tests (pytest)
docs/                       # Documentacion (ORIENTATION_FIX.md)
scripts/                    # build.py, build.spec, launcher.py, verify, etc.
```

## Empaquetar como binario (PyInstaller)

El proyecto incluye un wrapper multiplataforma (`scripts/build.py` +
`scripts/build.spec`) que produce un binario único listo para distribuir
o desplegar como servicio. Compila en **Windows** y en **Linux** (x86_64 /
arm64, p. ej. Orange Pi).

> **¿Por qué PyInstaller?** El driver USB-Serial (`pyserial` + `usb.core`)
> ya es portable. PyInstaller sólo agrupa Python + dependencias en un
> ejecutable que se puede copiar a otra máquina sin instalar nada.

### Requisitos previos

| Plataforma | Dependencia                                                | Notas                                                                                                                        |
| ---------- | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Windows    | Visual C++ Build Tools 2022 (Build Tools)                  | Lo instala el extension`C/C++` de VS. Sólo se necesita la primera vez para que `usb.core` pueda compilar si hace falta. |
| Linux      | `build-essential`, `python3-dev`, `libusb-1.0-0-dev` | Para el backend C de`pyusb` y la extensión `pyserial`.                                                                  |
| Ambos      | `uv` + `PyInstaller` (ya en `pyproject.toml`)        | Se instala automáticamente con`uv sync`.                                                                                  |

### Windows

#### ¿Cuándo se necesita Visual C++ Build Tools?

`pyusb` y `pyserial` traen **binarios precompilados en Windows** (`*.whl`)
para CPython 3.12 x64 — pero al hacer `uv sync` puede intentar
recompilarlos si la versión del wheel no coincide. Si ves:

```
error: Microsoft Visual C++ 14.0 or greater is required.
Get it with "Microsoft C++ Build Tools": https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

instala **Visual Studio Build Tools 2022** con el workload
**"Desarrollo para escritorio con C++"** (esto descarga ~6 GB).

> Si `uv sync` resuelve wheels precompilados (lo habitual con Python
> 3.12 x64), puedes saltarte este paso y volver aquí solo si falla.

#### Instalación paso a paso

```powershell
# 0. (Opcional, solo si falla uv sync) Instalar Visual Studio Build Tools 2022:
#    https://visualstudio.microsoft.com/visual-cpp-build-tools/
#    Marca "Desarrollo para escritorio con C++" en el instalador.
#    Reinicia PowerShell al terminar.

# 1. Instalar uv (si no lo tienes)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Cierra y vuelve a abrir PowerShell para que el PATH tome efecto.

# 2. Instalar Git para Windows (si no lo tienes)
#    https://git-scm.com/download/win

# 3. Clonar el repo
git clone <repo>
cd turing-display-controller

# 4. Sincronizar dependencias (crea .venv con PyInstaller ya dentro)
uv sync

# 5. Compilar el binario
uv run python scripts/build.py

# Salida:
#   dist\turing-display-controller\turing-display-controller.exe
#   (junto con su carpeta _internal\ con las DLLs)
```

#### Probar el binario antes de distribuirlo

```powershell
# Necesita config.ini en la misma carpeta que el .exe
Copy-Item config.ini dist\turing-display-controller\config.ini

# Ejecutar desde PowerShell (verás logs en la consola)
cd dist\turing-display-controller
.\turing-display-controller.exe
```

Si la pantalla muestra el slideshow y el dashboard abre en
`http://127.0.0.1:8000`, el build está OK. `Ctrl+C` para parar.

#### Empaquetar como ZIP distribuible

```powershell
# Crear ZIP portable (incluye _internal\)
Compress-Archive -Path dist\turing-display-controller `
    -DestinationPath turing-display-controller-windows-x64.zip

# El usuario final solo necesita:
#   1. Descomprimir el ZIP
#   2. Instalar driver CH340/CH341 si Windows no reconoce la pantalla
#   3. Editar config.ini (com_port = COM5, etc.)
#   4. Doble clic en turing-display-controller.exe
```

Notas Windows:

- El `.exe` se puede copiar a cualquier carpeta y ejecutar con doble clic.
- Si el path tiene espacios (p. ej. `C:\Mis Programas\...`) no hay problema.
- **Driver USB-Serial**: el `.exe` necesita el driver CH340/CH341
  instalado en la máquina destino. Ver [Instalación en Windows](#instalación-en-windows).
- **Antivirus**: algunos AV marcan binarios PyInstaller como sospechosos
  la primera vez. Es un falso positivo conocido
  ([PyInstaller issue #4693](https://github.com/pyinstaller/pyinstaller/issues/4693)).
  Solución: añadir excepción para la carpeta `dist\turing-display-controller\`.

#### Troubleshooting específico de Windows

| Síntoma                                                                                          | Causa                                                | Solución                                                                                                                        |
| ------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `error: Microsoft Visual C++ 14.0 or greater is required` al hacer `uv sync`                  | Falta MSVC Build Tools                               | Instala[VS Build Tools 2022](https://visualstudio.microsoft.com/visual-cpp-build-tools/) con workload C++.                        |
| `OSError: [WinError 126] No se puede encontrar el módulo especificado` al ejecutar el `.exe` | Falta una DLL nativa en`_internal\`                | Reconstruye con`uv run python scripts/build.py --clean` y vuelve a copiar toda la carpeta `dist\turing-display-controller\`. |
| `PermissionError: [Errno 13] Permission denied: 'COM5'` desde el `.exe`                       | Otra app tiene COM5 abierto (p. ej. la versión dev) | Cierra la app dev primero, o cambia`com_port` en `config.ini`.                                                               |
| `FileNotFoundError: 'COM5'` desde el `.exe`                                                   | El`.exe` no encuentra `config.ini`               | Coloca`config.ini` en la misma carpeta que el `.exe`.                                                                        |
| Antivirus borra`turing-display-controller.exe`                                                  | Falso positivo de PyInstaller                        | Añade excepción en Windows Defender o desactiva temporalmente.                                                                 |
| `pyinstaller: command not found`                                                                | `uv sync` no instaló PyInstaller                  | Verifica`pyproject.toml` tiene `pyinstaller` en `[dependency-groups] dev`. Corre `uv sync --group dev`.                  |
| `ImportError: attempted relative import with no known parent package` al ejecutar el binario   | El spec usaba`__main__.py` directo (sin `__package__`) | El spec actual usa `scripts/launcher.py` como entry. Reconstruye: `uv run python scripts/build.py --clean`. |

### Linux (Debian / Ubuntu / Orange Pi)

```bash
# 1. Dependencias nativas del sistema
sudo apt update
sudo apt install -y build-essential python3-dev libusb-1.0-0-dev \
                    libudev-dev pkg-config git

# 2. Clonar e instalar Python deps (incluye PyInstaller)
git clone <repo>
cd turing-display-controller
uv sync

# 3. Compilar el binario
uv run python scripts/build.py

# Salida:
#   dist/turing-display-controller/turing-display-controller
```

Notas Linux:

- En **Orange Pi** o SBC ARM compila **en la propia placa** (cross-compile
  es complicado para `pyusb`). Tiempo típico: 2–4 min.
- Haz el binario ejecutable si lo descargas desde otro sitio:
  `chmod +x turing-display-controller`.
- Las **reglas udev** del display se instalan igual que en la versión
  dev. Ver [Instalación en Debian/Orange Pi](#instalación-en-debianorange-pi).

### Estructura del binario generado

```
dist/turing-display-controller/
├── turing-display-controller(.exe)   # binario principal
├── _internal/                        # librerías y assets
│   ├── Pillow.libs/...
│   ├── libusb-1.0.dll  (Win) / libusb-1.0.so.0 (Linux)
│   └── ...
└── ...
```

> **Importante:** distribuye **toda la carpeta** `dist/turing-display-controller/`,
> no solo el ejecutable. Las dependencias `_internal/` son obligatorias.

### Instalación como servicio Linux

La guía completa de despliegue en Linux/Orange Pi (binario compilado +
systemd + config + actualización + desinstalación) está en
[**Instalación en Debian / Orange Pi (arm64)**](#instalación-en-debian--orange-pi-arm64),
paso 3 en adelante. Todo se ejecuta con `sudo` sobre el binario de
`/opt/turing-display-controller/`, nunca desde un venv.

### Instalación como servicio Windows

Usa [NSSM](https://nssm.cc/) o Task Scheduler:

```powershell
# Con NSSM (recomendado):
nssm install TuringDisplay "C:\Program Files\turing-display-controller\turing-display-controller.exe"
nssm set TuringDisplay AppDirectory "C:\Program Files\turing-display-controller"
nssm set TuringDisplay AppEnvironmentExtra TD_CONFIG=C:\ProgramData\turing-display\config.ini
nssm set TuringDisplay Start SERVICE_AUTO_START
nssm start TuringDisplay
```

### Troubleshooting de compilación

| Síntoma                                                            | Causa probable                              | Solución                                                                        |
| ------------------------------------------------------------------- | ------------------------------------------- | -------------------------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'X'` al ejecutar el binario | Falta un hidden import en`build.spec`     | Añade`hiddenimports=['X']` en `scripts/build.spec` y vuelve a compilar.     |
| `error: Microsoft Visual C++ 14.0 or greater is required`         | Falta Build Tools en Windows                | Instala Visual Studio Build Tools 2022 con "Desarrollo de escritorio con C++".   |
| `fatal error: libusb.h: No such file or directory`                | Falta dev de libusb en Linux                | `sudo apt install libusb-1.0-0-dev`.                                           |
| Binario muy grande (>200 MB)                                        | Estática Matplotlib/PyQt por error         | Limpia dependencias no usadas en`pyproject.toml`.                              |
| `OSError: [Errno 13] Permission denied: '/dev/ttyUSB0'`           | Falta regla udev o no estás en`dialout`  | Ver sección[Instalación en Debian/Orange Pi](#instalación-en-debianorange-pi). |
| En Windows:`FileNotFoundError: 'COM5'` desde el `.exe`          | El`.exe` no ve `config.ini` junto a él | Coloca`config.ini` en la misma carpeta que el `.exe`.                        |

### Compilar el `.exe` con PyInstaller directo

El wrapper (`scripts/build.py`) sólo es un atajo. Lo que realmente
genera el ejecutable es **PyInstaller** leyendo `scripts/build.spec`.
Si quieres ver exactamente qué pasa o personalizar opciones, llama
a PyInstaller directo:

```powershell
# Windows (PowerShell)
uv run pyinstaller --noconfirm --clean scripts\build.spec
```

```bash
# Linux (bash)
uv run pyinstaller --noconfirm --clean scripts/build.spec
```

#### ¿Qué produce exactamente?

```
dist/
└── turing-display-controller/
    ├── turing-display-controller.exe        # ← el ejecutable de Windows
    ├── _internal/                           # DLLs + Python runtime + libs
    │   ├── python312.dll
    │   ├── libusb-1.0.dll
    │   ├── PIL/                             # Pillow
    │   ├── serial/                          # pyserial
    │   ├── fastapi/, uvicorn/, ...
    │   └── ...
    └── (otros recursos especificados en build.spec)
```

> **Importante:** distribuye **toda la carpeta** `dist/turing-display-controller/`,
> no solo el `.exe`. Las dependencias en `_internal/` son obligatorias.

#### Cómo se llama el ejecutable

El nombre sale de `scripts/build.spec`:

```python
# En scripts/build.spec
exe = EXE(
    ...,
    name='turing-display-controller',   # ← este es el nombre del .exe
    ...
)
```

Así que en Windows produce **`turing-display-controller.exe`** y en
Linux **`turing-display-controller`** (sin extensión). Ambos quedan
dentro de `dist/turing-display-controller/`.

#### Opciones útiles de PyInstaller

```bash
# Build incremental (más rápido, conserva caché)
uv run pyinstaller scripts\build.spec

# Limpiar caché antes de buildear (build "desde cero")
uv run pyinstaller --clean --noconfirm scripts\build.spec

# Ver qué se incluye / qué falta (debug)
uv run pyinstaller --log-level DEBUG scripts\build.spec

# Empaquetar todo en un único .exe (más lento al arrancar, +
#    sensible a antivirus — NO recomendado para este proyecto)
uv run pyinstaller --onefile scripts\build.spec
```

#### Personalizar el `.spec`

Si necesitas cambiar el icono, añadir archivos extra (p. ej. fonts),
o agregar un `hidden import`, edita `scripts/build.spec`:

```python
# Añadir un archivo de datos (ej: fuente TTF propia)
datas=[
    ('assets/fonts/MiFuente.ttf', 'assets/fonts'),
],

# Forzar inclusión de un módulo que PyInstaller no detecta
hiddenimports=[
    'PIL._tkinter_finder',
    'usb.backend.libusb1',
],

# Cambiar el icono del .exe
exe = EXE(
    ...,
    icon='assets/icon.ico',   # solo Windows
)
```

Después de modificar el `.spec`, vuelve a buildear con
`uv run pyinstaller --noconfirm --clean scripts\build.spec`.

`scripts/build.spec` ya define todas las opciones (`onefile=False`,
`console=True`, datos, hidden imports, icono).

---

## Licencia

GPL-3.0

## Documentación adicional

- **`docs/ORIENTATION_FIX.md`**: Regla de oro de la rotación del panel, trucos, y bugs arreglados.
