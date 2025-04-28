import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import pydeck as pdk
from datetime import datetime

# 🗭 Configuration de la page
st.set_page_config(page_title="Logistique distribution", layout="wide")

# 🌍 Initialisation du géolocaliseur
geolocator = Nominatim(user_agent="tournees_app")

# 🚚 Paramètres à saisir
st.sidebar.header("🚚 Paramètres des camions")
nombre_camions = st.sidebar.number_input("Nombre de camions :", min_value=1, max_value=50, value=3)
CAPACITES_CAMIONS = {}

col1, col2, col3 = st.sidebar.columns(3)
plaques = []
poids_list = []
volume_list = []
for i in range(nombre_camions):
    plaque = col1.text_input(f"Plaque #{i+1}", value=f"7835{i+9}-A-7", key=f"plaque_{i}")
    poids = col2.number_input(f"Poids max #{i+1} (kg)", min_value=1000, max_value=50000, value=3500, step=100, key=f"poids_{i}")
    volume = col3.number_input(f"Volume max #{i+1} (m³)", min_value=1.0, max_value=100.0, value=15.0, step=0.5, key=f"volume_{i}")
    CAPACITES_CAMIONS[plaque] = {"poids": poids, "volume": volume}
CAMIONS = list(CAPACITES_CAMIONS.keys())

# 🧠 Paramètres de groupage
st.sidebar.header("🧠 Paramètres de groupage")
rayon_groupage_km = st.sidebar.number_input("Rayon maximal de groupage (en km) :", min_value=1, max_value=50, value=10, step=1)

# 📌 Fonction de géocodage ville -> (lat, lon)
def geocoder_ville(ville):
    try:
        location = geolocator.geocode(ville)
        return (location.latitude, location.longitude) if location else (None, None)
    except:
        return (None, None)

# 🕒 Vérification de chevauchement horaire
def horaires_se_chevauchent(h1, h2):
    try:
        debut1, fin1 = [datetime.strptime(h, "%H:%M") for h in h1.split("-")]
        debut2, fin2 = [datetime.strptime(h, "%H:%M") for h in h2.split("-")]
        return max(debut1, debut2) < min(fin1, fin2)
    except:
        return False

# 📦 Optimisation avec groupage et plages horaires
def optimiser_tournees(commandes, ville, jour):
    commandes_restantes = sorted(commandes, key=lambda x: x['volume'], reverse=True)
    tournees = []
    camion_idx = 0
    index = 1

    while commandes_restantes:
        tournee = []
        poids_total = 0
        volume_total = 0

        i = 0
        while i < len(commandes_restantes):
            cmd = commandes_restantes[i]
            if CAMIONS:
                camion_actuel = CAMIONS[camion_idx % len(CAMIONS)]
                poids_max = CAPACITES_CAMIONS.get(camion_actuel, {}).get("poids", 3500)
                volume_max = CAPACITES_CAMIONS.get(camion_actuel, {}).get("volume", 15)
            else:
                poids_max = 3500
                volume_max = 15

            if poids_total + cmd['poids'] <= poids_max and volume_total + cmd['volume'] <= volume_max:
                if not tournee:
                    tournee.append(cmd)
                    poids_total += cmd['poids']
                    volume_total += cmd['volume']
                    commandes_restantes.pop(i)
                else:
                    dist = geodesic((cmd['lat'], cmd['lon']), (tournee[0]['lat'], tournee[0]['lon'])).km
                    if dist <= rayon_groupage_km and horaires_se_chevauchent(cmd['heures_de_travail'], tournee[0]['heures_de_travail']):
                        tournee.append(cmd)
                        poids_total += cmd['poids']
                        volume_total += cmd['volume']
                        commandes_restantes.pop(i)
                    else:
                        i += 1
            else:
                i += 1

        camion_attribue = camion_actuel if CAMIONS else "Aucun"
        camion_idx += 1

        tournees.append({
            'index': index,
            'ville': ville,
            'jour': jour,
            'poids_total': poids_total,
            'volume_total': volume_total,
            'clients': tournee,
            'camion': camion_attribue
        })
        index += 1

    return tournees

# 🌐 Interface
st.title("🚚 Optimisation des Tournées par Camion")
fichier = st.file_uploader("Importer le fichier Excel des commandes :", type=["xlsx"])

if fichier:
    try:
        df_clients = pd.read_excel(fichier)
        colonnes_attendues = ['id_client', 'nom', 'prenom', 'volume', 'poids', 'ville', 'jour_de_travail', 'heures_de_travail']

        if not all(col in df_clients.columns for col in colonnes_attendues):
            st.error("❌ Le fichier ne contient pas toutes les colonnes nécessaires.")
        else:
            coords = df_clients['ville'].apply(geocoder_ville)
            df_clients['lat'] = coords.apply(lambda x: x[0])
            df_clients['lon'] = coords.apply(lambda x: x[1])

            tournees = []
            groupes = df_clients.groupby(['ville', 'jour_de_travail'])
            for (ville, jour), commandes in groupes:
                commandes_list = commandes.to_dict(orient='records')
                tournees += optimiser_tournees(commandes_list, ville, jour)

            for t in tournees:
                st.markdown(f"### 🙻 Tournée #{t['index']} - Ville: {t['ville']} | Jour: {t['jour']} | Camion: `{t['camion']}`")
                st.write(f"📦 {t['poids_total']} kg | 🖐 {t['volume_total']} m³")
                df_tournee = pd.DataFrame(t['clients'])
                st.dataframe(df_tournee[['id_client', 'nom', 'prenom', 'volume', 'poids', 'heures_de_travail']])

            st.markdown("## 📜 Carte des tournées")
            carte_data = df_clients.dropna(subset=['lat', 'lon'])
            st.pydeck_chart(pdk.Deck(
                map_style='mapbox://styles/mapbox/streets-v11',
                initial_view_state=pdk.ViewState(
                    latitude=carte_data['lat'].mean(),
                    longitude=carte_data['lon'].mean(),
                    zoom=6,
                    pitch=0,
                ),
                layers=[
                    pdk.Layer(
                        'ScatterplotLayer',
                        data=carte_data,
                        get_position='[lon, lat]',
                        get_radius=5000,
                        get_fill_color='[200, 30, 0, 160]',
                        pickable=True
                    ),
                ],
            ))

    except Exception as e:
        st.error(f"❌ Erreur lors de l'importation du fichier : {e}")

