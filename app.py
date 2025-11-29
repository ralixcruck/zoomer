import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv
import time
import pydeck as pdk

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="NetHunter (ZoomEye Edition) - Búsqueda de Dispositivos en Red",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CARGAR VARIABLES DE ENTORNO ---
load_dotenv()
API_KEY = os.getenv("ZOOMEYE_API_KEY")

if not API_KEY:
    st.error("❌ La API Key de ZoomEye no se encontró. Asegúrate de tener un archivo `.env` con tu `ZOOMEYE_API_KEY`.")
    st.stop()

# --- FUNCIONES ---
def zoomeye_search(query, page=1):
    url = "https://api.zoomeye.org/host/search"
    params = {"query": query, "page": page}
    headers = {"API-KEY": API_KEY}
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error al consultar la API: {e}")
        return None

def parse_zoomeye_data(data):
    matches = data.get('matches', [])
    if not matches:
        return pd.DataFrame()

    parsed_list = []
    for item in matches:
        ip = item.get('ip', 'N/A')
        port = item.get('port', 0)
        protocol = item.get('protocol', 'N/A')
        geoinfo = item.get('geoinfo', {})
        country = geoinfo.get('country', {}).get('names', {}).get('en', 'N/A')
        city = geoinfo.get('city', {}).get('names', {}).get('en', 'N/A')
        latitude = geoinfo.get('latitude', None)
        longitude = geoinfo.get('longitude', None)
        banner = item.get('data', 'N/A')
        product_info = item.get('product', '')
        version_info = item.get('version', '')
        product = f"{product_info} {version_info}".strip()

        parsed_list.append({
            "ip_str": ip,
            "port": port,
            "transport": protocol,
            "country": country,
            "city": city,
            "lat": latitude,
            "lon": longitude,
            "product": product if product else "N/A",
            "data": banner
        })
    return pd.DataFrame(parsed_list)

def classify_device(row):
    product = str(row['product']).lower()
    port = row['port']
    banner = str(row['data']).lower()
    
    # Cámaras IP
    if 'camera' in product or 'hikvision' in product or 'dahua' in product or port in [554, 8000, 8080]:
        return "Cámara IP"
    # Servidores web
    elif any(x in product for x in ['nginx', 'apache', 'iis']) or port in [80, 443, 8080]:
        return "Servidor Web"
    # Bases de datos
    elif any(x in product for x in ['mysql', 'mariadb', 'postgres', 'mongodb']) or port in [3306, 5432, 27017]:
        return "Base de Datos"
    # Servidores / ordenadores
    elif port in [22, 2222]:
        return "Servidor/Ordenador (SSH)"
    elif port in [23]:
        return "Dispositivo de red (Telnet)"
    # IoT genérico
    elif any(x in banner for x in ['iot', 'smart', 'home', 'device']):
        return "IoT"
    else:
        return "Desconocido"

def port_color(row):
    dtype = row['device_type']
    if dtype == "Cámara IP":
        return [255, 0, 0, 160]  # Rojo
    elif dtype == "Servidor Web":
        return [0, 0, 255, 160]  # Azul
    elif dtype == "Base de Datos":
        return [255, 165, 0, 160]  # Naranja
    elif dtype == "Servidor/Ordenador (SSH)":
        return [0, 200, 0, 160]  # Verde
    elif dtype == "IoT":
        return [128, 0, 128, 160]  # Morado
    else:
        return [200, 30, 0, 160]  # Otro

# --- INTERFAZ ---
st.title("🔭 NetHunter (ZoomEye Edition)")
st.markdown("Búsqueda y análisis de dispositivos en red con filtros avanzados y mapa interactivo.")

# --- BARRA LATERAL ---
st.sidebar.header("🔍 Filtros de Búsqueda")
with st.sidebar.form("filter_form"):
    query = st.text_input("Consulta ZoomEye (DSL):", placeholder="Ej: port:8080, nginx, country:ES")
    country_filter = st.text_input("Filtrar por país (ISO 2 letras, ej: US, ES):")
    port_filter = st.text_input("Filtrar por puerto(s) separados por coma (Ej: 22,80,443):")
    device_text_filter = st.text_input("Filtrar por nombre de dispositivo/servicio (texto libre):")
    device_type_filter = st.selectbox("Filtrar por tipo de dispositivo:", [""])
    submitted = st.form_submit_button("🚀 Ejecutar Búsqueda")

# --- EJECUCIÓN ---
if submitted:
    if not query:
        st.warning("Introduce una consulta para ZoomEye.")
        st.stop()

    progress_bar = st.progress(0)
    status_text = st.empty()
    for i in range(1, 101):
        status_text.text(f"Consultando la API de ZoomEye... {i}%")
        progress_bar.progress(i)
        time.sleep(0.01)
    status_text.text("¡Búsqueda completada!")
    time.sleep(0.5)
    progress_bar.empty()
    status_text.empty()

    api_data = zoomeye_search(query)
    
    if api_data:
        results_df = parse_zoomeye_data(api_data)
        if results_df.empty:
            st.error("No se encontraron resultados.")
            st.stop()

        # Clasificar dispositivos
        results_df['device_type'] = results_df.apply(classify_device, axis=1)
        results_df['color'] = results_df.apply(port_color, axis=1)

        # --- FILTROS ---
        if country_filter:
            results_df = results_df[results_df['country'].str.upper() == country_filter.upper()]
        if port_filter:
            try:
                ports = [int(p.strip()) for p in port_filter.split(',')]
                results_df = results_df[results_df['port'].isin(ports)]
            except ValueError:
                st.warning("Puerto(s) inválido(s), se ignorará el filtro.")
        if device_text_filter:
            results_df = results_df[results_df['product'].str.contains(device_text_filter, case=False, na=False)]
        if device_type_filter:
            if device_type_filter != "":
                results_df = results_df[results_df['device_type'] == device_type_filter]

        if results_df.empty:
            st.error("No se encontraron dispositivos que coincidan con los criterios.")
            st.stop()

        st.success(f"✅ Se encontraron {len(results_df)} dispositivos.")

        # --- TABLA ---
        st.subheader("📋 Resultados en tabla")
        st.dataframe(results_df.drop(columns=['data', 'color']))

        # CSV
        csv = results_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar CSV", csv, "zoomeye_results.csv", "text/csv")

        # --- DETALLES ---
        st.subheader("🔎 Detalles por dispositivo")
        for idx, row in results_df.iterrows():
            with st.expander(f"{row['ip_str']}:{row['port']} - {row['product']} ({row['device_type']})"):
                st.write(f"**IP:** {row['ip_str']}")
                st.write(f"**Puerto:** {row['port']} ({row['transport']})")
                st.write(f"**País / Ciudad:** {row['country']} / {row['city']}")
                st.write(f"**Producto / Versión:** {row['product']}")
                st.write(f"**Tipo de dispositivo:** {row['device_type']}")
                st.write(f"**Banner / Metadata:** {row['data']}")

        # --- MAPA INTERACTIVO ---
        map_df = results_df.dropna(subset=['lat', 'lon'])
        if not map_df.empty:
            st.subheader("🌍 Ubicación de los dispositivos")
            layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position='[lon, lat]',
                get_color='color',
                get_radius=50000,
                pickable=True
            )
            view_state = pdk.ViewState(
                latitude=map_df['lat'].mean(),
                longitude=map_df['lon'].mean(),
                zoom=2,
                pitch=0
            )
            r = pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip={"text": "IP: {ip_str}\nPuerto: {port}\nProducto: {product}\nTipo: {device_type}\nPaís: {country}\nCiudad: {city}"}
            )
            st.pydeck_chart(r)
        else:
            st.info("No hay coordenadas disponibles para mostrar en el mapa.")
