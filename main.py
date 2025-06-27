import os
import sys
import threading
import csv
import glob
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from TwitchChannelPointsMiner import TwitchChannelPointsMiner
from TwitchChannelPointsMiner.classes.Settings import Settings
from TwitchChannelPointsMiner.classes.entities.Bet import Strategy, BetSettings
from TwitchChannelPointsMiner.classes.entities.Streamer import Streamer
from TwitchChannelPointsMiner.logger import LoggerSettings

# Servidor HTTP simple para health checks
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        
    def log_message(self, format, *args):
        # Evitar logging de requests HTTP
        return

def run_health_server():
    port = int(os.getenv('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

def clean_logs_if_needed(max_size_mb=20):
    """Limpia logs si superan el tamaño máximo"""
    current_dir = Path(__file__).parent.absolute()
    log_files = glob.glob(str(current_dir / "*.log"))
    
    total_size = 0
    for log_file in log_files:
        try:
            total_size += os.path.getsize(log_file)
        except OSError:
            continue
    
    # Convertir a MB
    total_size_mb = total_size / (1024 * 1024)
    
    if total_size_mb > max_size_mb:
        print(f"📁 Limpiando logs ({total_size_mb:.1f}MB > {max_size_mb}MB)")
        for log_file in log_files:
            try:
                os.remove(log_file)
            except OSError:
                pass
        print("✅ Logs limpiados")

def get_file_modification_time(file_path):
    """Obtiene la fecha de modificación del archivo"""
    try:
        return os.path.getmtime(file_path)
    except OSError:
        return 0

def read_streamers_from_csv():
    """Lee la lista de streamers desde streamers.csv"""
    current_dir = Path(__file__).parent.absolute()
    csv_path = current_dir / 'streamers.csv'
    
    streamers = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            content = file.read().strip()
            # Separar por comas y limpiar espacios
            streamer_names = [name.strip() for name in content.split(',') if name.strip()]
            
            # Validar que los streamers no estén vacíos
            valid_streamers = []
            for name in streamer_names:
                if len(name) > 0 and name.replace('_', '').replace('-', '').isalnum():
                    valid_streamers.append(Streamer(name))
                    print(f"✅ Streamer válido: {name}")
                else:
                    print(f"⚠️  Streamer inválido ignorado: '{name}'")
            
            streamers = valid_streamers
            print(f"📺 Cargados {len(streamers)} streamers válidos: {', '.join([s.username for s in streamers])}")
            
    except FileNotFoundError:
        print(f"⚠️  No se encontró {csv_path}")
        print("Creando archivo con streamer por defecto...")
        with open(csv_path, 'w', encoding='utf-8') as file:
            file.write("mixwell")
        streamers = [Streamer("mixwell")]
    except Exception as e:
        print(f"❌ Error leyendo streamers: {e}")
        print("Usando streamer por defecto...")
        streamers = [Streamer("mixwell")]
    
    if not streamers:
        print("⚠️  No hay streamers válidos, usando mixwell por defecto")
        streamers = [Streamer("mixwell")]
    
    return streamers

def monitor_csv_changes(twitch_miner, check_interval=300):
    """Monitorea cambios en el archivo CSV cada 5 minutos por defecto"""
    current_dir = Path(__file__).parent.absolute()
    csv_path = current_dir / 'streamers.csv'
    
    last_modified = get_file_modification_time(csv_path)
    
    while True:
        time.sleep(check_interval)  # Esperar 5 minutos
        
        try:
            current_modified = get_file_modification_time(csv_path)
            
            if current_modified > last_modified:
                print("🔄 Detectado cambio en streamers.csv")
                last_modified = current_modified
                
                # Leer nuevos streamers
                new_streamers = read_streamers_from_csv()
                
                # Actualizar la lista de streamers del minero
                if hasattr(twitch_miner, 'streamers'):
                    old_streamers = [s.username for s in twitch_miner.streamers]
                    new_streamer_names = [s.username for s in new_streamers]
                    
                    if old_streamers != new_streamer_names:
                        print(f"🔄 Actualizando streamers: {old_streamers} → {new_streamer_names}")
                        twitch_miner.streamers = new_streamers
                        print("✅ Lista de streamers actualizada")
                    else:
                        print("ℹ️  No hay cambios en la lista de streamers")
                else:
                    print("⚠️  No se pudo acceder a la lista de streamers del minero")
                    
        except Exception as e:
            print(f"❌ Error monitoreando cambios en CSV: {e}")

def run_twitch_miner():
    """Ejecuta el minero de Twitch en un hilo separado"""
    # Obtiene las credenciales desde las variables del sistema
    username = os.getenv('TWITCH_USERNAME')
    password = os.getenv('TWITCH_PASSWORD')

    if not username or not password:
        print("❌ Error: No se encontraron las credenciales en las variables del sistema")
        print("Asegúrate de que las variables TWITCH_USERNAME y TWITCH_PASSWORD están configuradas")
        return

    # Configuración del logger minimalista
    logger_settings = LoggerSettings(
        save=False,  # No guardar logs en archivo
        less=False,  # Cambiado a False para mostrar más información
        console_level=10,  # Cambiado a DEBUG para ver más actividad
        file_level=30,     # WARNING level 
        emoji=True,
        colored=True,
        auto_clear=True,   # Limpiar logs automáticamente
        console_username=True  # Cambiado a True para ver el username
    )

    print(f"🚀 Iniciando TwitchWatcher para usuario: {username}")
    print("📝 Configuración del logger ajustada para mostrar más información")

    # Inicialización del minero
    twitch_miner = TwitchChannelPointsMiner(
        username=username,
        password=password,
        logger_settings=logger_settings
    )

    # Configurar los ajustes después de la inicialización
    Settings.check_interval = 30  # Reducido a 30 segundos para más actividad
    Settings.make_predictions = False
    Settings.follow_raid = True
    Settings.claim_drops = True
    Settings.watch_streak = True
    Settings.auto_claim_bonuses = True
    Settings.disable_ssl_cert_verification = True
    Settings.enable_analytics = True  # Habilitado para las analíticas web
    Settings.chat_online = False

    # Configurar path de analíticas (CRÍTICO para evitar el error)
    current_dir = Path(__file__).parent.absolute()
    Settings.analytics_path = str(current_dir / "analytics")

    # Crear directorio de analytics si no existe
    analytics_dir = Path(Settings.analytics_path)
    analytics_dir.mkdir(exist_ok=True)

    # Obtener puerto desde variable de entorno (Koyeb asigna automáticamente)
    port = int(os.getenv('PORT', 8080))  # 8080 como fallback para desarrollo local
    
    # Configurar analíticas web en el puerto principal
    print(f"📊 Iniciando servidor de analíticas en puerto {port}")
    print(f"🌐 HTTPS habilitado automáticamente por Koyeb")
    
    twitch_miner.analytics(
        host="0.0.0.0",  # Permitir acceso desde cualquier IP
        port=port,       # Usar el puerto asignado por Koyeb (dinámico)
        refresh=5,       # Refrescar cada 5 minutos
        days_ago=30      # Mostrar últimos 30 días
    )

    # Leer streamers desde CSV
    streamers = read_streamers_from_csv()

    # Iniciar tareas en segundo plano
    background_thread = threading.Thread(target=background_tasks, args=(twitch_miner,), daemon=True)
    background_thread.start()

    print("✅ Configuración completada, iniciando minado...")
    print("🔍 Monitor de cambios en CSV activado (revisa cada 5 minutos)")
    print(f"🌐 Analíticas disponibles en el puerto {port}")
    print("🔒 HTTPS/2 manejado automáticamente por Koyeb")
    print("⏱️  Verificando cada 30 segundos...")
    print("")
    print("🔑 IMPORTANTE: Si aparece un código de activación:")
    print("   1. Ve a https://www.twitch.tv/activate")
    print("   2. Introduce el código mostrado")
    print("   3. El bot continuará automáticamente")
    print("")

    # Agregar logging adicional para debug
    print("🔧 Configuración actual:")
    print(f"   - Streamers: {[s.username for s in streamers]}")
    print(f"   - Check interval: {Settings.check_interval}s")
    print(f"   - Analytics habilitado: {Settings.enable_analytics}")
    print("🎯 Iniciando minado...")

    # Ejecutar el miner EN EL HILO PRINCIPAL (necesario para las señales del sistema)
    try:
        twitch_miner.run(streamers)
    except KeyboardInterrupt:
        print("\n🛑 Deteniendo TwitchWatcher...")
        sys.exit(0)

def background_tasks(twitch_miner):
    """Ejecuta tareas en segundo plano"""
    # Iniciar monitor de cambios en CSV
    csv_monitor_thread = threading.Thread(
        target=monitor_csv_changes, 
        args=(twitch_miner, 300),  # Revisar cada 5 minutos
        daemon=True
    )
    csv_monitor_thread.start()
    
    # Limpiar logs periódicamente
    while True:
        time.sleep(300)  # Revisar cada 5 minutos
        clean_logs_if_needed()

# Limpiar logs antes de empezar
clean_logs_if_needed()

# Obtiene las credenciales desde las variables del sistema
username = os.getenv('TWITCH_USERNAME')
password = os.getenv('TWITCH_PASSWORD')

if not username or not password:
    print("❌ Error: No se encontraron las credenciales en las variables del sistema")
    print("Asegúrate de que las variables TWITCH_USERNAME y TWITCH_PASSWORD están configuradas")
    sys.exit(1)

# Configuración del logger minimalista
logger_settings = LoggerSettings(
    save=False,  # No guardar logs en archivo
    less=False,  # Cambiado a False para mostrar más información
    console_level=10,  # Cambiado a DEBUG para ver más actividad
    file_level=30,     # WARNING level 
    emoji=True,
    colored=True,
    auto_clear=True,   # Limpiar logs automáticamente
    console_username=True  # Cambiado a True para ver el username
)

print(f"🚀 Iniciando TwitchWatcher para usuario: {username}")
print("📝 Configuración del logger ajustada para mostrar más información")

# Inicialización del minero EN EL HILO PRINCIPAL
twitch_miner = TwitchChannelPointsMiner(
    username=username,
    password=password,
    logger_settings=logger_settings
)

# Configurar los ajustes después de la inicialización
Settings.check_interval = 30  # Reducido a 30 segundos para más actividad
Settings.make_predictions = False
Settings.follow_raid = True
Settings.claim_drops = True
Settings.watch_streak = True
Settings.auto_claim_bonuses = True
Settings.disable_ssl_cert_verification = True
Settings.enable_analytics = True  # Habilitado para las analíticas web
Settings.chat_online = False

# Configurar path de analíticas (CRÍTICO para evitar el error)
current_dir = Path(__file__).parent.absolute()
Settings.analytics_path = str(current_dir / "analytics")

# Crear directorio de analytics si no existe
analytics_dir = Path(Settings.analytics_path)
analytics_dir.mkdir(exist_ok=True)

# Obtener puerto desde variable de entorno
port = int(os.getenv('PORT', 8080))

# Configurar analíticas web en el puerto principal
print(f"📊 Iniciando servidor de analíticas en puerto {port}")
print(f"🌐 HTTPS habilitado automáticamente por Koyeb")

twitch_miner.analytics(
    host="0.0.0.0",  # Permitir acceso desde cualquier IP
    port=port,       # Usar el puerto asignado por Koyeb
    refresh=5,       # Refrescar cada 5 minutos
    days_ago=30      # Mostrar últimos 30 días
)

# Leer streamers desde CSV
streamers = read_streamers_from_csv()

# Iniciar tareas en segundo plano
background_thread = threading.Thread(target=background_tasks, args=(twitch_miner,), daemon=True)
background_thread.start()

print("✅ Configuración completada, iniciando minado...")
print("🔍 Monitor de cambios en CSV activado (revisa cada 5 minutos)")
print(f"🌐 Analíticas disponibles en el puerto {port}")
print("🔒 HTTPS/2 manejado automáticamente por Koyeb")
print("⏱️  Verificando cada 30 segundos...")
print("")
print("🔑 IMPORTANTE: Si aparece un código de activación:")
print("   1. Ve a https://www.twitch.tv/activate")
print("   2. Introduce el código mostrado")
print("   3. El bot continuará automáticamente")
print("")

# Agregar logging adicional para debug
print("🔧 Configuración actual:")
print(f"   - Streamers: {[s.username for s in streamers]}")
print(f"   - Check interval: {Settings.check_interval}s")
print(f"   - Analytics habilitado: {Settings.enable_analytics}")
print("🎯 Iniciando minado...")

# Ejecutar el miner EN EL HILO PRINCIPAL (necesario para las señales del sistema)
try:
    twitch_miner.run(streamers)
except KeyboardInterrupt:
    print("\n🛑 Deteniendo TwitchWatcher...")
    sys.exit(0)
