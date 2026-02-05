import pandas as pd #ignore
import plotly.express as px
import streamlit as st
import requests
from urllib.parse import urljoin 
import numpy as np
from PIL import Image
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import re
from collections import Counter
from difflib import get_close_matches
import os
from dotenv import load_dotenv
# from sqlalchemy import create_engine

#Layout da página
st.set_page_config(
    page_title="Estudos em Doenças Raras",
	layout="wide"
    )
caminho_logo = 'Logo svri texto preto.png'  
st.sidebar.image(caminho_logo, use_container_width=True)  

# url = 'postgresql://db_nap_clinicaltrials_user:DVh4H1qjtyTF6N3X7hf4mb1mSddWPa57@dpg-cr7m52btq21c73d9vnhg-a.ohio-postgres.render.com/clinical'
 
# engine = create_engine(
#     url,
#     pool_pre_ping=True,
#     # pool_recycle=300,
   
# )

############################################## Acessando a API da Polo Trials ##############################################
load_dotenv()

@st.cache_data
def ler_api():
    api_username = os.getenv('API_USERNAME')
    api_password = os.getenv('API_PASSWORD')
    api_url = os.getenv("API_URL")
    auth_url = urljoin(api_url, "/sessions")

    body = {
        "nome": api_username,
        "password":api_password
    }

    response = requests.post(auth_url, json=body)
    token = response.json()['token']
    auth_token = "Bearer " + token

    # Requisição para obter os dados do protocolo
    protocolo_url = urljoin(api_url, "/protocolo?nested=true")
    headers = {"Authorization": auth_token}

    response = requests.get(protocolo_url, headers=headers)
    protocolos = response.json()
    polo = pd.DataFrame(protocolos)
    
    return polo

polo = ler_api()

############################ Upload da base de dados: Clinical Trials (tratado anteriormente e salvo localmente) ############################
@st.cache_data
def ler_excel():
    resultado = dr_ct = pd.read_excel("Base_Nova.xlsx", sheet_name= 0)
    return resultado

#Título da Página principal
st.write("# Doenças Raras: Estudos feitos pela Indústria")

clinical = ler_excel()
clinical = clinical[['NCT Number','Study Title','Study URL','Funder Type', 'Sponsor','Collaborators','Enrollment', 'Start Date','First Posted', 'Nome do Arquivo', 'Estudo no Brasil','Study Status', 'Phases','Interventions', 'Intervention_type']]
clinical1 = clinical[clinical['Funder Type'].str.contains('INDUSTRY')]
clinical1['Study Status'] = clinical1['Study Status'].str.replace('_', ' ', regex=False)


# PAGINA PRINCIPAL:
estudos_mundo = clinical1[['NCT Number', 'Nome do Arquivo','Sponsor','Enrollment', 'Estudo no Brasil','Collaborators','Study URL','Study Status', 'Phases', 'Start Date','First Posted','Interventions', 'Intervention_type']]
estudos_mundo['Nome do Arquivo'] = clinical1['Nome do Arquivo'].str.replace('.csv', '', regex=False)
estudos_mundo['Sponsor'] = estudos_mundo['Sponsor'].str.upper()
estudos_mundo['Nome do Arquivo'] = estudos_mundo['Nome do Arquivo'].str.title()
estudos_mundo = estudos_mundo.drop_duplicates()

estudos = clinical1["NCT Number"].nunique()
estudos1 = clinical1[clinical1["Estudo no Brasil"] == "SIM"]["NCT Number"].nunique()


col1, col2, col3, col4, col5, col6 = st.columns(6)

with col3:
    sponsor = sorted(estudos_mundo["Sponsor"].unique())
    patrocinadores = st.selectbox("**Patrocinadores**", ['Selecionar Todos'] + sponsor, index=0, placeholder="Selecione a empresa...")

with col4:
    status = sorted(estudos_mundo['Study Status'].unique())
    status_estudos = st.selectbox("**Status do Estudo**", ['Selecionar Todos'] + status, index=0, placeholder="Selecione status...")

with col5:
    estudos_nomes = sorted(estudos_mundo['Nome do Arquivo'].unique())  
    nome_estudo = st.selectbox("**Comorbidade:**", ['Selecionar Todos'] + estudos_nomes, index=0, placeholder="Selecione o nome do estudo...")

if patrocinadores == 'Selecionar Todos' and status_estudos == 'Selecionar Todos' and nome_estudo == 'Selecionar Todos':
    item_df = estudos_mundo
elif patrocinadores == 'Selecionar Todos' and status_estudos == 'Selecionar Todos':
    item_df = estudos_mundo[estudos_mundo["Nome do Arquivo"] == nome_estudo]
elif patrocinadores == 'Selecionar Todos' and nome_estudo == 'Selecionar Todos':
    item_df = estudos_mundo[estudos_mundo["Study Status"] == status_estudos]
elif status_estudos == 'Selecionar Todos' and nome_estudo == 'Selecionar Todos':
    item_df = estudos_mundo[estudos_mundo["Sponsor"] == patrocinadores]
elif patrocinadores == 'Selecionar Todos':
    item_df = estudos_mundo[(estudos_mundo["Study Status"] == status_estudos) & (estudos_mundo["Nome do Arquivo"] == nome_estudo)]
elif status_estudos == 'Selecionar Todos':
    item_df = estudos_mundo[(estudos_mundo["Sponsor"] == patrocinadores) & (estudos_mundo["Nome do Arquivo"] == nome_estudo)]
elif nome_estudo == 'Selecionar Todos':
    item_df = estudos_mundo[(estudos_mundo["Sponsor"] == patrocinadores) & (estudos_mundo["Study Status"] == status_estudos)]
else:
    item_df = estudos_mundo[(estudos_mundo["Sponsor"] == patrocinadores) & (estudos_mundo["Study Status"] == status_estudos) & (estudos_mundo["Study Name"] == nome_estudo)]

filtered_estudos_mundo = item_df["NCT Number"].nunique()
filtered_estudos_brasil = item_df[item_df["Estudo no Brasil"] == "SIM"]["NCT Number"].nunique()

with col1:
    st.metric("**TOTAL MUNDO:**", filtered_estudos_mundo)

with col2:
    st.metric("**TOTAL BRASIL:**", filtered_estudos_brasil)

color_sequence = ['#EC0E73', '#041266', '#00A1E0', '#C830A0', '#61279E']

tab1, tab2, tab3 = st.tabs(["**MUNDO**", "**BRASIL**", "**PARCEIROS SVRI**"])
with tab1:
    df_contagem = item_df.groupby('Sponsor')['NCT Number'].nunique().reset_index(name='num_estudos')
    df_top10 = df_contagem.sort_values(by='num_estudos', ascending=False).head(20)
    df_contagem_comorbidade = item_df.groupby('Nome do Arquivo')['NCT Number'].nunique().reset_index(name='num_estudos')
    df_top10_comorbidade = df_contagem_comorbidade.sort_values(by='num_estudos', ascending=False).head(20)
    df_contagem_fase = item_df.groupby('Phases')['NCT Number'].nunique().reset_index(name='num_estudos')
    df_intervencoes = item_df.groupby('Intervention_type')['NCT Number'].nunique().reset_index(name='num_estudos')
    df_tipo_intervencoes = df_intervencoes.sort_values(by='num_estudos', ascending=False).head(10)
    df_tipo_intervencoes['Intervention_type'] = df_tipo_intervencoes['Intervention_type'].str.upper()
    df_colaboradores = item_df.groupby('Collaborators')['NCT Number'].nunique().reset_index(name='num_estudos')
    df_colaboradores1 = df_colaboradores.sort_values(by='num_estudos', ascending=False).head(10)

    ful1,ful2 = st.columns([3,3])
    with ful1:
        #### GRÁFICO DAS 20 EMPRESAS COM MAIOR NÚMERO DE ESTUDOS ####
        fig = px.bar(df_top10, x="num_estudos", y="Sponsor", color='Sponsor', color_discrete_sequence= color_sequence, orientation= 'h', text='num_estudos', height=400)
        fig.update_traces(texttemplate='%{text:.0f}', textposition='outside', cliponaxis=False, showlegend=False)
        fig.update_layout(xaxis_title='', yaxis_title='', uniformtext_minsize=6, uniformtext_mode='hide', yaxis=dict(tickfont=dict(size=10)))
        st.subheader('TOP 20 EMPRESAS COM MAIOR NÚMERO DE ESTUDOS')
        st.write('O gráfico abaixo mostra as 10 empresas com maior número de estudos:')
        st.plotly_chart(fig)

        #### GRÁFICO DAS 20 COMORBIDADES COM MAIORES NÚMEROS DE ESTUDOS ####
        fig = px.bar(df_top10_comorbidade, x="num_estudos", y="Nome do Arquivo", color='Nome do Arquivo', color_discrete_sequence= color_sequence, text='num_estudos', height=500)
        fig.update_traces(texttemplate='%{text:.0f}', textposition='outside', cliponaxis=False, showlegend=False)
        fig.update_layout(xaxis_title='', yaxis_title='', uniformtext_minsize=6, uniformtext_mode='hide', yaxis=dict(tickfont=dict(size=10)))        
        st.subheader('TOP 20 MAIORES COMORBIDADES')
        st.write('O gráfico abaixo mostra as 10 comorbidades com maiores números de estudos:')
        st.plotly_chart(fig)
        
        #### GRÁFICO DAS 10 PRINCIPAIS CRO'S ####
        df_colaboradores1['Collaborators'] = df_colaboradores1['Collaborators'].replace('-', 'Sem CRO')
        fig = px.bar(df_colaboradores1, x="Collaborators", y="num_estudos", color='Collaborators', color_discrete_sequence= color_sequence, text='num_estudos', height=400)
        fig.update_traces(texttemplate='%{text:.0f}', textposition='outside', cliponaxis=False, showlegend=False)
        fig.update_layout(xaxis_title='', yaxis_title='', uniformtext_minsize=6, uniformtext_mode='hide', yaxis=dict(tickfont=dict(size=10)))        
        st.subheader('AS PRINCIPAIS COLADORADORAS')
        st.write('O gráfico abaixo mostra as principais empresas colaboradoras em estudos:')
        st.plotly_chart(fig)

    with ful2:
        #### GRÁFICO COM ESTUDOS POR FASE ####
        fig = px.bar(df_contagem_fase, x="Phases", y="num_estudos", color='Phases', color_discrete_sequence= color_sequence, text='num_estudos', height=400)
        fig.update_traces(texttemplate='%{text:.0f}', textposition='outside', cliponaxis=False, showlegend=False)
        fig.update_layout(xaxis_title='', yaxis_title='',uniformtext_minsize=8, uniformtext_mode='hide')
        st.subheader('ESTUDOS POR FASE')
        st.write('O gráfico abaixo mostra a quantidade de estudos por fase:')
        st.plotly_chart(fig)

        #### GRÁFICO DE LINHAS NUMERO DE ESTUDOS POR ANO ####
        item_df['First Posted'] = pd.to_datetime(item_df['First Posted'], format='%Y-%m-%d', errors='coerce')
        item_df = item_df.dropna(subset=['First Posted'])
        item_df['Year'] = item_df['First Posted'].dt.year
        studies_per_year = item_df.groupby('Year')['NCT Number'].nunique().reset_index(name='Number of Studies')
        fig = px.line(studies_per_year,x='Year',y='Number of Studies',title='Número de Estudos por Ano',labels={'Year': 'Ano', 'Number of Studies': 'Número de Estudos'}, markers=True)
        fig.update_layout(
            xaxis_title='',
            yaxis_title='',
            xaxis=dict(tickformat='%Y'),
            yaxis=dict(tickfont=dict(size=8)), 
            title_font=dict(size=14),
            margin=dict(l=40, r=10, t=40, b=40)  
        )
        fig.update_traces(line=dict(color='purple'))
        st.subheader('NÚMERO DE ESTUDOS POR ANO')
        st.write('O gráfico abaixo mostra o número de estudos realizados a cada ano:')
        st.plotly_chart(fig)

        #### GRÁFICO DOS TIPOS DE INTERVENÇÕES POR ESTUDOS ####
        fig = px.bar(df_tipo_intervencoes, x="Intervention_type", y="num_estudos", color='Intervention_type',  color_discrete_sequence= color_sequence, text='num_estudos', height=400)
        fig.update_traces(texttemplate='%{text:.0f}', textposition='outside', cliponaxis=False, showlegend=False)
        fig.update_layout(xaxis_title='', yaxis_title='', uniformtext_minsize=6, uniformtext_mode='hide', yaxis=dict(tickfont=dict(size=10)))        
        st.subheader('TIPOS DE INTERVENÇÃO')
        st.write('O gráfico mostra o tipo de intervenção por número de estudos:')
        st.plotly_chart(fig)

    #### TABELA COM DADOS DAS EMPRESAS E SEUS ESTUDOS ####
    st.write('Listagem completa de todos os estudos:')
    item_df.rename(columns={'Nome do Arquivo': 'Comorbidade', 'Sponsor': 'Patrocinador','Enrollment': 'Participantes', 'Collaborators': 'Colaboradores', 'Phases': 'Fase do Estudo'}, inplace=True)
    df_clinical = item_df[['Study URL','Comorbidade', 'Patrocinador', 'Participantes', "Estudo no Brasil",'Study Status', 'Colaboradores', 'Fase do Estudo']]
    st.dataframe(df_clinical, column_config= {'Study URL': st.column_config.LinkColumn('NCT Number')}, hide_index=True)
    
with tab2:
    col1, col2 = st.columns(2)
    ### Estudos no Brasil ###
    with col1:
        df_brasil = df_clinical[df_clinical['Estudo no Brasil'] == 'SIM']
        df_contagem = df_brasil.groupby('Patrocinador')['Study URL'].nunique().reset_index(name='num_estudos')
        fig = px.bar(df_contagem, x="num_estudos", y="Patrocinador", color="Patrocinador", color_discrete_sequence= color_sequence, orientation= 'h', height=600)
        fig.update_layout(
            xaxis_title='',
            yaxis_title='',
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01,
                visible=False 
            ),
            title=''
        )
        st.subheader('Estudos realizados no Brasil')
        st.write('O gráfico abaixo mostra os estudos que estão sendo realizados em território nacional:')
        st.plotly_chart(fig)
        
    with col2:
    #### GRÁFICO COM ESTUDOS POR FASE ####
        fig = px.bar(df_contagem_fase, x="num_estudos", y="Phases", color='Phases', color_discrete_sequence= color_sequence, orientation= 'h', text='num_estudos', height=400)
        # fig = px.pie(df_contagem_fase, values='num_estudos', names='Phases', title='Estudos x Fase', color_discrete_sequence=px.colors.sequential.RdBu)
        fig.update_traces(texttemplate='%{text:.0f}', textposition='outside', cliponaxis=False, showlegend=False)
        fig.update_layout(xaxis_title='', yaxis_title='',uniformtext_minsize=8, uniformtext_mode='hide')
        st.subheader('ESTUDOS POR FASE')
        st.write('O gráfico abaixo mostra a quantidade de estudos por fase:')
        st.plotly_chart(fig)

    st.write('Listagem de estudos no Brasil:')
    df_brasil = df_brasil.sort_values(by='Patrocinador', ascending=True)
    df_brasil = df_brasil[['Study URL','Comorbidade', 'Patrocinador', 'Participantes', "Estudo no Brasil",'Study Status', 'Colaboradores', 'Fase do Estudo']]
    st.dataframe(df_brasil, column_config= {'Study URL': st.column_config.LinkColumn('NCT Number')}, hide_index=True)

with tab3:
############################################## CRUZANDO NOSSA BASE COM A POLO TRIAL  ############################################## 
    sponsors = polo[['numero_protocolo','patrocinador', 'dados_patrocinador','dados_tipo_de_estudo','dados_especialidade', 'status']]
    def extrair_ultima_informacao(x):
        if isinstance(x, dict):
            values_list = list(x.values())
            return values_list[-1] if values_list else None
        elif isinstance(x, str):
            return x 
        else:
            return None
    colunas_data_polotrial = ['numero_protocolo','dados_patrocinador', 'dados_tipo_de_estudo', 'dados_especialidade', 'status']
    for coluna in colunas_data_polotrial:
        sponsors[coluna] = sponsors[coluna].apply(extrair_ultima_informacao)

    sponsors.rename(columns={'numero_protocolo': 'Protocolo', 'dados_patrocinador': 'Patrocinador','dados_tipo_de_estudo': 'Tipos de Estudo',  'dados_especialidade': 'Especialidade','status': 'Status'}, inplace=True)

    sponsors['Protocolo'].replace(['', ' ', 'nan', np.nan], np.nan, inplace=True)
    estudos_brasil1 = sponsors[sponsors['Protocolo'].notna()]
    estudos_brasil2 = estudos_brasil1[sponsors['Status'] != 'Concluído']
    estudos_brasil = estudos_brasil2.drop_duplicates()
    estudos_polo = estudos_brasil["Protocolo"].count()

    ####### ESTRUTURA DA ABA - POLO TRIAL #######
    ful1,ful2 = st.columns([3,2])

    with ful1: 
    ####### NUVEM DE PALAVRAS COM AS ESPECIALIDADES #######
        def normalize_text(text):
            text = text.strip().upper() 
            return re.sub(r'[^\w\s]', '', text) 

        estudos_brasil['Especialidade'] = estudos_brasil['Especialidade'].fillna('')
        estudos_brasil['Especialidade'] = estudos_brasil['Especialidade'].apply(normalize_text)
        text = ' '.join(estudos_brasil['Especialidade'])
        word_freq = Counter(text.split())

        unique_words = list(word_freq.keys())
        for word in unique_words:
            matches = get_close_matches(word, unique_words, n=5, cutoff=0.8)  # Altera cutoff conforme necessário
            if len(matches) > 1:
                print(f'Possíveis duplicatas para "{word}": {matches}')

        def custom_color_func(word, font_size, position, orientation, random_state=None, **kwargs):
            return np.random.choice(color_sequence)

        wordcloud = WordCloud(
            width=800,
            height=400,
            background_color='white',
            color_func=custom_color_func
        ).generate_from_frequencies(word_freq)

        fig, ax = plt.subplots(figsize=(5, 3)) 
        ax.imshow(wordcloud, interpolation='bilinear')
        ax.axis("off")
        st.pyplot(fig)

     ####### ESTUDOS REALIZADOS POR NOSSOS PARCEIROS #######

        estudos_brasil['Patrocinador'] = estudos_brasil['Patrocinador'].str.upper()

        df_filtrado = df_clinical[df_clinical['Patrocinador'].isin(estudos_brasil['Patrocinador'])]
        st.subheader('Estudos Clínicos de Indústrias Parceiras:')
        col1, col2, col3 = st.columns(3)

        filtro_brasil = st.selectbox('Filtrar estudos realizados no Brasil:', ['Todos', 'SIM', 'NÃO'])
        if filtro_brasil != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['Estudo no Brasil'] == filtro_brasil]

        contagem_estudos = df_filtrado["Study URL"].nunique()
        filtered_brasil = df_filtrado[df_filtrado["Estudo no Brasil"] == "SIM"]["Study URL"].nunique()

        with col1:
            st.metric("**Nossos parceiros: MUNDO**", contagem_estudos)

        with col2: 
            st.metric("**Nossos parceiros: BRASIL**", filtered_brasil)

        df_merged = pd.merge(df_filtrado, estudos_brasil, on='Patrocinador', how='inner')
        poloect = df_merged[['Study URL', 'Protocolo', 'Comorbidade', 'Patrocinador', 
                            'Estudo no Brasil', 'Study Status', 'Colaboradores', 
                            'Fase do Estudo', 'Tipos de Estudo', 'Especialidade', 'Status']]

        poloect = poloect.drop_duplicates(subset=['Study URL', 'Protocolo'])

        st.dataframe(poloect, column_config={'Study URL': st.column_config.LinkColumn('NCT Number')}, hide_index=True)
   
    ####### GRÁFICO COM CRO's #######
        poloect['Colaboradores'] = poloect['Colaboradores'].replace('-', 'Sem CRO')
        estudos_br = poloect.groupby('Colaboradores').size().reset_index(name='Número de Protocolos')
        fig = px.bar(estudos_br, x="Colaboradores", y="Número de Protocolos",color='Colaboradores',color_discrete_sequence= color_sequence, text='Número de Protocolos', height=400)
        fig.update_traces(texttemplate='%{text:.0f}', textposition='outside', cliponaxis=False, showlegend=False)
        fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
        st.subheader('Lista de Colaboradores na Polo:')
        st.write('O gráfico abaixo mostra o número de estudos por CRO:')
        st.plotly_chart(fig)
        

    with ful2:
    ####### GRÁFICOS HORIZONTAL COM NÚMERO DE ESTUDOS ABERTOS POR EMPRESA #######
        estudos_br = estudos_brasil.groupby('Patrocinador').size().reset_index(name='Número de Protocolos')

        estudos_br = estudos_br.sort_values(by='Número de Protocolos', ascending=False)
        fig = px.bar(estudos_br, 
                    x='Número de Protocolos', 
                    y='Patrocinador', 
                    color='Patrocinador', text='Número de Protocolos',
                    color_discrete_sequence= color_sequence, orientation='h', 
                    height=2000)

        fig.update_traces(texttemplate='%{text:.0f}', textposition='outside', cliponaxis=False)
        fig.update_layout(
            xaxis_title='', 
            yaxis_title='', 
            yaxis=dict(
                tickfont=dict(size=9)
            ),
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01,
                visible=False
            ),
            title='',
            width=600,
            height=1600
        )

        st.write('**Número de estudos por Empresa**')
        st.plotly_chart(fig)

st.sidebar.title('PESQUISAS EM DOENÇAS RARAS')
st.sidebar.markdown("Desenvolvido por [Science Valley Reseach Institute](https://svriglobal.com/)")
