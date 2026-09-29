import streamlit as st
import xml.etree.ElementTree as ET
import math
import random
import pandas as pd
import folium
import requests
from streamlit_folium import st_folium

# --- 1. FUNÇÕES DO MOTOR DE OTIMIZAÇÃO ---
def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calcular_fitness(rota):
    dist_total = 0
    for i in range(len(rota) - 1):
        dist_total += calcular_distancia_metros(rota[i]['lat'], rota[i]['lon'], rota[i+1]['lat'], rota[i+1]['lon'])
    return dist_total

def gerar_rota_logica_base(pontos):
    nao_visitados = pontos.copy()
    atual = nao_visitados.pop(0)
    rota = [atual]
    while nao_visitados:
        mais_proximo = min(nao_visitados, key=lambda p: calcular_distancia_metros(atual['lat'], atual['lon'], p['lat'], p['lon']))
        rota.append(mais_proximo)
        nao_visitados.remove(mais_proximo)
        atual = mais_proximo
    return rota

# --- 2. INTEGRAÇÃO COM GPS (DESENHO NAS RUAS) ---
def obter_tracado_ruas(rota_otimizada):
    coordenadas = [[p['lat'], p['lon']] for p in rota_otimizada]
    linhas_rua = []
    
    tamanho_bloco = 40
    for i in range(0, len(coordenadas), tamanho_bloco - 1):
        bloco = coordenadas[i:i + tamanho_bloco]
        if len(bloco) < 2:
            break
            
        coords_str = ";".join([f"{lon},{lat}" for lat, lon in bloco])
        url = f"http://router.project-osrm.org/route/v1/walking/{coords_str}?overview=full&geometries=geojson"
        
        try:
            resposta = requests.get(url)
            if resposta.status_code == 200:
                dados = resposta.json()
                coords_gps = dados['routes'][0]['geometry']['coordinates']
                linhas_rua.extend([[c[1], c[0]] for c in coords_gps])
            else:
                linhas_rua.extend(bloco) 
        except:
            linhas_rua.extend(bloco)
            
    return linhas_rua

# --- 3. INTERFACE PROFISSIONAL DO SISTEMA ---
st.set_page_config(page_title="Gestão de Rotas - SGL", layout="wide")

st.title("📍 Módulo de Roteamento de Leituras")
st.markdown("Sistema integrado para sequenciamento otimizado de pastas baseado em geolocalização.")

if 'rota_pronta' not in st.session_state:
    st.session_state.rota_pronta = None
if 'distancia_final' not in st.session_state:
    st.session_state.distancia_final = 0
if 'tracado_ruas' not in st.session_state:
    st.session_state.tracado_ruas = []

st.sidebar.header("📁 Importação de Dados")
arquivos_kml = st.sidebar.file_uploader("Selecione a carga do dia (.kml)", type=["kml"], accept_multiple_files=True)

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Parâmetros do Motor")
st.sidebar.caption("Configurações do Algoritmo de Otimização")
tamanho_pop = st.sidebar.slider("Capacidade de Processamento", 10, 200, 100, help="Quantidade de cenários simulados simultaneamente.")
geracoes = st.sidebar.slider("Ciclos de Sequenciamento", 50, 500, 200)
taxa_mutacao = st.sidebar.slider("Fator de Desvio", 0.01, 0.5, 0.1)

if arquivos_kml:
    pontos = []
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    
    for arquivo in arquivos_kml:
        tree = ET.parse(arquivo)
        root = tree.getroot()
        for placemark in root.findall('.//kml:Placemark', ns):
            nome_tag = placemark.find('kml:name', ns)
            coord_tag = placemark.find('.//kml:coordinates', ns)
            if coord_tag is not None:
                nome = nome_tag.text if nome_tag is not None else f"Leitura {len(pontos)+1}"
                coords = coord_tag.text.strip().split(',')
                pontos.append({
                    "uid": len(pontos), 
                    "id": nome, 
                    "lat": float(coords[1]), 
                    "lon": float(coords[0])
                })
            
    st.info(f"Base de dados carregada: **{len(pontos)}** pontos de medição detetados.")

    if st.button("Processar Sequenciamento Otimizado", type="primary"):
        st.toast("A iniciar motor de cálculo logístico...", icon="⏳")
        barra_progresso = st.progress(0, text="A calcular trajetórias...")
        
        populacao = [random.sample(pontos, len(pontos)) for _ in range(tamanho_pop - 1)]
        populacao.append(gerar_rota_logica_base(pontos))
        
        # Correção do passo de progresso para evitar divisão por zero
        passo_progresso = max(1, geracoes // 100)
        
        for geracao in range(geracoes):
            populacao.sort(key=calcular_fitness)
            nova_geracao = populacao[:int(tamanho_pop * 0.3)]
            
            while len(nova_geracao) < tamanho_pop:
                pai1, pai2 = random.sample(populacao[:int(tamanho_pop * 0.5)], 2)
                corte1, corte2 = sorted(random.sample(range(len(pontos)), 2))
                filho = [None] * len(pontos)
                filho[corte1:corte2] = pai1[corte1:corte2]
                
                p2_idx = 0
                for i in range(len(pontos)):
                    if filho[i] is None:
                        while pai2[p2_idx] in filho:
                            p2_idx += 1
                        filho[i] = pai2[p2_idx]
                        
                if random.random() < taxa_mutacao:
                    idx1, idx2 = random.sample(range(len(pontos)), 2)
                    filho[idx1], filho[idx2] = filho[idx2], filho[idx1]
                nova_geracao.append(filho)
            populacao = nova_geracao
            
            if geracao % passo_progresso == 0:
                barra_progresso.progress(geracao / geracoes, text=f"A otimizar... Ciclo {geracao}/{geracoes}")
                
        barra_progresso.progress(1.0, text="A finalizar traçado das ruas...")
        
        melhor_rota = populacao[0]
        st.session_state.rota_pronta = melhor_rota
        st.session_state.distancia_final = calcular_fitness(melhor_rota)
        st.session_state.tracado_ruas = obter_tracado_ruas(melhor_rota)
        
    # --- 4. EXIBIÇÃO DOS RESULTADOS (DASHBOARD) ---
    if st.session_state.rota_pronta is not None:
        st.divider()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total de Leituras", len(st.session_state.rota_pronta))
        m2.metric("Distância do Trajeto", f"{(st.session_state.distancia_final / 1000):.2f} km")
        m3.metric("Tempo Est. (a pé)", f"{int((st.session_state.distancia_final / 1000) * 12)} min")
        
        col_mapa, col_tabela = st.columns([2, 1])
        
        with col_mapa:
            st.subheader("🗺️ Traçado Operacional")
            
            # Mapa gratuito padrão do Folium sem necessidade de API Key
            mapa_folium = folium.Map(
                location=[st.session_state.rota_pronta[0]['lat'], st.session_state.rota_pronta[0]['lon']], 
                zoom_start=17
            )
            
            folium.PolyLine(st.session_state.tracado_ruas, color="#FF4B4B", weight=5, opacity=0.9).add_to(mapa_folium)
            
            folium.Marker(
                [st.session_state.rota_pronta[0]['lat'], st.session_state.rota_pronta[0]['lon']], 
                popup="Ponto de Partida", 
                icon=folium.Icon(color="green", icon="play")
            ).add_to(mapa_folium)
            
            st_folium(mapa_folium, width="100%", height=500, returned_objects=[])
            
        with col_tabela:
            st.subheader("📋 Relatório de Sequenciamento")
            st.caption("Organize as suas pastas nesta ordem exata:")
            df_rota = pd.DataFrame(st.session_state.rota_pronta)
            df_rota.index += 1
            st.dataframe(df_rota[['id']], use_container_width=True, height=450)
else:
    st.info("👆 Aguarda importação da carga de leitura (.kml) no menu lateral para iniciar o módulo.")