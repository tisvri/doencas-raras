import requests
import pandas as pd
import time
import json
import logging
import os
from typing import List, Dict
from datetime import datetime
from pathlib import Path
import sys

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clinical_trials_download.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class ClinicalTrialsDownloader:
    """
    Downloader robusto de ensaios clínicos do ClinicalTrials.gov
    Com sistema de checkpoint e recuperação de erros
    """

    def __init__(self, checkpoint_file: str = "checkpoint.json"):
        self.base_url = "https://clinicaltrials.gov/api/v2/studies"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.checkpoint_file = checkpoint_file
        self.checkpoint_data = self._load_checkpoint()
        self.request_count = 0
        self.max_retries = 3

    def _load_checkpoint(self) -> Dict:
        """Carrega checkpoint se existir"""
        if Path(self.checkpoint_file).exists():
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"✓ Checkpoint carregado: {len(data.get('completed_diseases', []))} doenças já processadas")
                    return data
            except Exception as e:
                logger.warning(f"Erro ao carregar checkpoint: {e}")
        return {
            'completed_diseases': [],
            'studies': [],
            'last_update': None
        }

    def _save_checkpoint(self):
        """Salva checkpoint atual"""
        try:
            self.checkpoint_data['last_update'] = datetime.now().isoformat()
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(self.checkpoint_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Checkpoint salvo: {len(self.checkpoint_data['studies'])} estudos")
        except Exception as e:
            logger.error(f"Erro ao salvar checkpoint: {e}")

    def _wait_with_backoff(self, attempt: int):
        """Espera progressiva entre tentativas"""
        wait_time = min(2 ** attempt, 30)
        logger.info(f"Aguardando {wait_time}s antes de tentar novamente...")
        time.sleep(wait_time)

    def search_disease(self, disease_name: str, recruitment_status: List[str]) -> List[Dict]:
        """Busca estudos para uma doença com retry automático"""
        all_studies = []

        for status in recruitment_status:
            page_token = None
            page_num = 1

            while True:
                for attempt in range(self.max_retries):
                    try:
                        params = {
                            'query.cond': disease_name,
                            'filter.overallStatus': status,
                            'pageSize': 100,
                            'format': 'json'
                        }

                        if page_token:
                            params['pageToken'] = page_token

                        logger.debug(f"Requisição: {disease_name} ({status}) - Página {page_num}, Tentativa {attempt + 1}")

                        response = requests.get(
                            self.base_url,
                            params=params,
                            headers=self.headers,
                            timeout=45
                        )

                        self.request_count += 1

                        if response.status_code == 200:
                            data = response.json()

                            if 'studies' in data:
                                studies = data['studies']
                                all_studies.extend(studies)
                                logger.info(f"  ✓ {disease_name} ({status}) Pág.{page_num}: {len(studies)} estudos")

                            if 'nextPageToken' in data and data['nextPageToken']:
                                page_token = data['nextPageToken']
                                page_num += 1
                                time.sleep(1.5)
                                break
                            else:
                                return all_studies

                        elif response.status_code == 429:
                            logger.warning(f"Rate limit atingido. Aguardando...")
                            self._wait_with_backoff(attempt + 2)
                            continue

                        else:
                            logger.warning(f"Status {response.status_code} para {disease_name}")
                            if attempt < self.max_retries - 1:
                                self._wait_with_backoff(attempt)
                                continue
                            else:
                                return all_studies

                    except requests.exceptions.Timeout:
                        logger.warning(f"Timeout na requisição (tentativa {attempt + 1}/{self.max_retries})")
                        if attempt < self.max_retries - 1:
                            self._wait_with_backoff(attempt)
                            continue
                        else:
                            logger.error(f"Timeout definitivo para {disease_name} ({status})")
                            return all_studies

                    except requests.exceptions.ConnectionError as e:
                        logger.warning(f"Erro de conexão: {str(e)[:100]}")
                        if attempt < self.max_retries - 1:
                            self._wait_with_backoff(attempt)
                            continue
                        else:
                            logger.error(f"Erro de conexão definitivo para {disease_name}")
                            return all_studies

                    except Exception as e:
                        logger.error(f"Erro inesperado: {type(e).__name__}: {str(e)[:100]}")
                        if attempt < self.max_retries - 1:
                            self._wait_with_backoff(attempt)
                            continue
                        else:
                            return all_studies

                if page_token is None:
                    break

        return all_studies

    def extract_study_data(self, study: Dict) -> Dict:
        """Extrai campos do estudo"""
        try:
            protocol = study.get('protocolSection', {})
            identification = protocol.get('identificationModule', {})
            status = protocol.get('statusModule', {})
            conditions = protocol.get('conditionsModule', {})
            design = protocol.get('designModule', {})
            arms = protocol.get('armsInterventionsModule', {})
            eligibility = protocol.get('eligibilityModule', {})
            contacts = protocol.get('contactsLocationsModule', {})
            sponsor = protocol.get('sponsorCollaboratorsModule', {})

            nct_id = identification.get('nctId', '')

            extracted = {
                'NCT Number': nct_id,
                'Study Title': identification.get('officialTitle', identification.get('briefTitle', '')),
                'Study URL': f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else '',
                'Study Status': status.get('overallStatus', ''),
                'Conditions': '|'.join(conditions.get('conditions', [])),
                'Interventions': '|'.join([
                    f"{i.get('type', '')}:{i.get('name', '')}" 
                    for i in arms.get('interventions', [])
                ]),
                'Sponsor': sponsor.get('leadSponsor', {}).get('name', ''),
                'Collaborators': '|'.join([c.get('name', '') for c in sponsor.get('collaborators', [])]),
                'Sex': eligibility.get('sex', ''),
                'Age': f"{eligibility.get('minimumAge', '')} - {eligibility.get('maximumAge', '')}",
                'Phases': '|'.join(design.get('phases', [])),
                'Enrollment': str(design.get('enrollmentInfo', {}).get('count', '')),
                'Funder Type': sponsor.get('leadSponsor', {}).get('class', ''),
                'Study Type': design.get('studyType', ''),
                'Study Design': design.get('designInfo', {}).get('allocation', ''),
                'Start Date': status.get('startDateStruct', {}).get('date', ''),
                'Completion Date': status.get('completionDateStruct', {}).get('date', ''),
                'First Posted': status.get('studyFirstPostDateStruct', {}).get('date', ''),
                'Results First Posted': status.get('resultsFirstPostDateStruct', {}).get('date', ''),
                'Last Update Posted': status.get('lastUpdatePostDateStruct', {}).get('date', ''),
                'Locations': '|'.join([
                    f"{loc.get('facility', '')} - {loc.get('city', '')}, {loc.get('country', '')}"
                    for loc in contacts.get('locations', [])
                ])
            }

            return extracted

        except Exception as e:
            logger.error(f"Erro ao extrair dados do estudo: {str(e)}")
            return {}

    def process_diseases(self, diseases: List[str], save_interval: int = 3) -> pd.DataFrame:
        """Processa lista de doenças com checkpoint automático"""
        recruitment_status = ['RECRUITING', 'NOT_YET_RECRUITING']
        completed = set(self.checkpoint_data['completed_diseases'])

        remaining_diseases = [d for d in diseases if d not in completed]

        if not remaining_diseases:
            logger.info("✓ Todas as doenças já foram processadas!")
            return pd.DataFrame(self.checkpoint_data['studies'])

        logger.info(f"\n{'='*80}")
        logger.info(f"INICIANDO PROCESSAMENTO")
        logger.info(f"Total de doenças: {len(diseases)}")
        logger.info(f"Já processadas: {len(completed)}")
        logger.info(f"Restantes: {len(remaining_diseases)}")
        logger.info(f"{'='*80}\n")

        for idx, disease in enumerate(remaining_diseases, 1):
            try:
                logger.info(f"\n[{len(completed) + idx}/{len(diseases)}] Processando: {disease}")

                studies = self.search_disease(disease, recruitment_status)

                if studies:
                    for study in studies:
                        extracted = self.extract_study_data(study)
                        if extracted:
                            extracted['Disease_Searched'] = disease
                            self.checkpoint_data['studies'].append(extracted)

                    logger.info(f"  ✓ Total de estudos encontrados: {len(studies)}")
                else:
                    logger.info(f"  ⚠ Nenhum estudo encontrado")

                self.checkpoint_data['completed_diseases'].append(disease)
                completed.add(disease)

                if idx % save_interval == 0:
                    self._save_checkpoint()
                    logger.info(f"  💾 Checkpoint salvo ({len(self.checkpoint_data['studies'])} estudos)")

                time.sleep(2)

            except KeyboardInterrupt:
                logger.warning("\n⚠ Interrupção detectada! Salvando progresso...")
                self._save_checkpoint()
                logger.info("✓ Progresso salvo. Execute novamente para continuar.")
                sys.exit(0)

            except Exception as e:
                logger.error(f"Erro ao processar {disease}: {str(e)}")
                continue

        self._save_checkpoint()

        return pd.DataFrame(self.checkpoint_data['studies'])


def Tratamento(diretorio: str, nome_salvar_arquivo: str):
    """
    Função de tratamento dos dados baixados
    """
    logger.info("\n" + "="*80)
    logger.info("INICIANDO TRATAMENTO DOS DADOS")
    logger.info("="*80)

    # Lista para armazenar os dataframes de cada arquivo CSV
    lista_df = []

    # Iterar sobre todos os arquivos no diretório
    for arquivo in os.listdir(diretorio):
        if arquivo.endswith('.csv'):
            caminho_arquivo = os.path.join(diretorio, arquivo)
            df = pd.read_csv(caminho_arquivo)
            if 'Disease_Searched' in df.columns:
                df['Nome do Arquivo'] = df['Disease_Searched']
            else:
                df['Nome do Arquivo'] = "Disease_Searched_not_found"
            lista_df.append(df)
            logger.info(f"  ✓ Arquivo carregado: {arquivo}")

    if not lista_df:
        logger.error("Nenhum arquivo CSV encontrado no diretório!")
        return

    # Concatenar todos os dataframes
    df = pd.concat(lista_df, ignore_index=True)
    logger.info(f"\n  Total de registros: {len(df)}")

    # Preencher valores nulos
    df['Interventions'].fillna('No intervention', inplace=True)
    df['Phases'].fillna('No Phases', inplace=True)
    df['Locations'] = df['Locations'].fillna('Pais não definido')
    df.fillna("-", inplace=True)

    # Remover duplicatas
    df = df.drop_duplicates(subset=['NCT Number'], keep='first')
    logger.info(f"  Após remoção de duplicatas: {len(df)} registros")

    # Processar Locations
    df['Locations'] = df['Locations'].str.split('|')
    df = df.explode('Locations')
    df['Pais'] = df['Locations'].apply(lambda x: x.split(',')[-1].strip() if pd.notna(x) else 'Pais não definido')

    # Strings a verificar para correção de países
    strings_a_verificar = [
        "Ascension and Tristan da Cunha", "Bolivarian Republic of", "British",
        "Democratic People's Republic of", "Federated States of",
        "Islamic Republic of", "Plurinational State of",
        "Province of China", "Republic of", "Sint Eustatius and Saba",
        "State of", "The Democratic Republic of the", "U.S.",
        "United Republic of"
    ]

    verifica_str = df['Pais'].str.contains('|'.join(strings_a_verificar), na=False)
    df.loc[verifica_str, 'Pais'] = df.loc[verifica_str, 'Locations'].apply(
        lambda x: ', '.join(x.split(',')[-2:]) if pd.notna(x) else 'Pais não definido'
    )
    df['Pais'] = df['Pais'].str.strip()

    # Países faltantes
    paises_faltantes = [
        'Pais não definido', 'Macedonia, The Former Yugoslav Republic of', 
        'Turkey', 'Taiwan', 'Czech Republic', 'Vietnam', 'Venezuela', 'Bolivia', 
        'Tanzania', 'Netherlands Antilles', 'Virgin Islands (U.S.)', 'Aland Islands'
    ]

    nomes_paises = df['Pais'].unique().tolist() + paises_faltantes
    df = df[df['Pais'].isin(nomes_paises)]

    # Corrigir ordem das palavras nos países
    df['Pais_corrigido'] = df['Pais']
    for index, pais in df['Pais'].items():
        if pd.notna(pais) and ',' in pais:
            parts = pais.split(', ')
            if len(parts) == 2:
                df.at[index, 'Pais_corrigido'] = ' '.join(parts[::-1])
            elif len(parts) > 2:
                df.at[index, 'Pais_corrigido'] = ', '.join(parts[-1:] + parts[:-1])

    df['Pais'] = df['Pais_corrigido']
    df.drop(columns=['Pais_corrigido'], inplace=True)

    # Agrupar países por NCT Number
    df_grouped = df.groupby([
        'NCT Number', 'Study Title', 'Study URL', 'Study Status', 'Conditions',
        'Interventions', 'Funder Type', 'Study Design', 'Sponsor', 'Collaborators',
        'Phases', 'Enrollment', 'Sex', 'Age', 'Study Type', 'Start Date','First Posted',
        'Completion Date', 'Nome do Arquivo'
    ])['Pais'].apply(lambda x: list(set(x))).reset_index()

    df_grouped.rename(columns={'Pais': 'Lista de Paises'}, inplace=True)

    # Verificar se Brasil está na lista
    df_grouped['Estudo no Brasil'] = df_grouped['Lista de Paises'].apply(
        lambda x: 'SIM' if 'Brazil' in x else 'NÃO'
    )

    # Expandir Conditions
    new_rows = []
    for index, row in df_grouped.iterrows():
        if pd.notna(row['Conditions']) and row['Conditions'] != '-':
            conds = row['Conditions'].split('|')
            for cond in conds:
                new_row = row.copy()
                new_row['Conditions'] = cond.strip()
                new_rows.append(new_row)
        else:
            new_rows.append(row)

    df_expanded = pd.DataFrame(new_rows)
    logger.info(f"  Após expandir Conditions: {len(df_expanded)} registros")

    # Expandir Collaborators
    nova_linha = []
    for index, row in df_expanded.iterrows():
        if pd.notna(row['Collaborators']) and row['Collaborators'] != '-':
            collabs = row['Collaborators'].split('|')
            for collab in collabs:
                new_row = row.copy()
                new_row['Collaborators'] = collab.strip()
                nova_linha.append(new_row)
        else:
            nova_linha.append(row)

    df_expanded2 = pd.DataFrame(nova_linha)
    logger.info(f"  Após expandir Collaborators: {len(df_expanded2)} registros")

    # Expandir Interventions
    linha = []
    for index, row in df_expanded2.iterrows():
        if pd.notna(row['Interventions']) and row['Interventions'] != '-' and row['Interventions'] != 'No intervention':
            intervs = row['Interventions'].split('|')
            for interv in intervs:
                new_row = row.copy()
                new_row['Interventions'] = interv.strip()
                linha.append(new_row)
        else:
            linha.append(row)

    df_final = pd.DataFrame(linha)
    logger.info(f"  Após expandir Interventions: {len(df_final)} registros")

    # Dividir Interventions em tipo e droga
    df_final['Drug'] = df_final['Interventions'].str.split(':').str[-1].str.strip()
    df_final['Intervention_type'] = df_final['Interventions'].str.split(':').str[0].str.strip()

    # Remover placebos
    df_final = df_final[~df_final['Drug'].str.contains('placebo', case=False, na=False)]
    logger.info(f"  Após remover placebos: {len(df_final)} registros")

    # Salvar arquivo
    caminho_saida = os.path.join(diretorio, nome_salvar_arquivo)
    df_final.to_excel(caminho_saida, index=False)

    logger.info(f"\n✓ Arquivo tratado salvo: {caminho_saida}")
    logger.info(f"  Total final de registros: {len(df_final)}")
    logger.info("="*80 + "\n")

    return df_final


def get_rare_diseases() -> List[str]:
    """Lista completa de doenças raras do arquivo fornecido"""
    return [
        # Allergic and Immunologic Disorders
        "Agammaglobulinemia",
        "Goodpasture Syndrome",
        "GPA, formerly Wegener Granulomatosis",
        "Leukocyte Adhesion Deficiency",
        "Pediatric Bruton Agammaglobulinemia",
        "Pediatric Severe Combined Immunodeficiency",
        "Schnitzler Syndrome",
        "X-Linked (Bruton) Agammaglobulinemia",


        # Benign Neoplasms
        "Birt-Hogg-Dube Syndrome",
        "Desmoid Tumor",
        "Drug-Induced Pemphigus",
        "Trevor Disease",
        "Familial Benign Pemphigus",
        "IgA Pemphigus",
        "Lymphangioleiomyomatosis",
        "Orthopedic Surgery for Fibrous Dysplasia",
        "Paraneoplastic Pemphigus",
        "Pemphigus Erythematosus",
        "Pemphigus Foliaceus",
        "Pemphigus Vulgaris",


        # Cancers
        "Anaplastic Thyroid Carcinoma",
        "Angiosarcoma",
        "Angiosarcoma of the Scalp",
        "Cholangiocarcinoma",
        "Cutaneous T-Cell Lymphoma",
        "Ewing Sarcoma",
        "Extragonadal Germ Cell Tumors",
        "Fibrolamellar Carcinoma",
        "Fibrolamellar Hepatocellular Carcinoma Imaging",
        "Follicular Thyroid Carcinoma",
        "Hereditary Nonpolyposis Colorectal Cancer",
        "Hurthle Cell Carcinoma",
        "Malignant Carcinoid Syndrome",
        "Malignant Mesothelioma",
        "Malignant Pleural Mesothelioma Staging",
        "Malignant Pleural Mesothelioma Treatment Protocols",
        "Medullary Thyroid Carcinoma",
        "Mesothelioma",
        "Basal Cell Nevus Syndrome",
        "Pancreatic Neuroendocrine",
        "Pediatric Pheochromocytoma",
        "Pediatric Thymoma",
        "Thymoma",
        "Thymoma Staging",
        "Thymoma Treatment Protocols",
        "WAGR Syndrome",
        "Waldenstrom Macroglobulinemia",
        "Waldenstrom Macroglobulinemia Treatment Protocols",


        # Cardiac and Vascular Conditions
        "Carney Complex",
        "Eisenmenger Syndrome",
        "Endocardial Fibroelastosis",
        "Endomyocardial Fibrosis",
        "Fibromuscular Dysplasia",
        "Holt-Oram Syndrome",
        "Idiopathic Pulmonary Arterial Hypertension",
        "Imaging in Fibromuscular Dysplasia of the Carotid Artery",
        "Pediatric Fungal Endocarditis",
        "Pediatric Holt-Oram Syndrome",
        "Pediatric Idiopathic Pulmonary Artery Hypertension",


        # Endocrine and Metabolic Disorders
        "Acquired Partial Lipodystrophy",
        "Acrodermatitis Enteropathica",
        "Alkaptonuria",
        "Carnitine Deficiency",
        "CTX",
        "Congenital Adrenal Hyperplasia",
        "Denys-Drash Syndrome",
        "Diabetes Insipidus",
        "Galactosemia",
        "Gaucher Disease",
        "Pompe Disease",
        "Propionyl CoA Carboxylase Deficiency",
        "Genetics of Tarui Disease",
        "Glycogen-Storage Disease Type 1",
        "Gigantism and Acromegaly",
        "Glycogen Storage Diseases Types I-VII",
        "Growth Hormone Resistance",
        "Mucopolysaccharidosis Type II",
        "Mucopolysaccharidosis Type I",
        "Hypophosphatemic Rickets",
        "Mucolipidosis Type II",
        "Kallmann Syndrome and Idiopathic Hypogonadotropic Hypogonadism",
        "Kearns-Sayre Syndrome",
        "Oculocerebrorenal Syndrome",
        "Lysosomal Storage Disease",
        "MSUD",
        "McCune-Albright Syndrome",
        "Metachromatic Leukodystrophy",
        "Mucopolysaccharidosis Type IV",
        "Mucopolysaccharidoses Types I-VII",
        "Mucopolysaccharidosis",
        "N-Acetylglutamate Synthetase Deficiency",
        "Ochronosis and Alkaptonuria",
        "Lowe Syndrome",
        "Ovotesticular Disorder of Sexual Development",
        "Pediatric Hypoparathyroidism",
        "Pheochromocytoma",
        "Pheochromocytoma Imaging",
        "Mucopolysaccharidosis Type III",
        "Mucolipidosis I",
        "Type Ia Glycogen Storage Disease",
        "Type Ib Glycogen Storage Disease",
        "Pompe Disease",
        "Type V Glycogen Storage Disease",
        "Type VI Glycogen Storage Disease",
        "Type VII Glycogen Storage Disease",
        "Variegate Porphyria",


        # Gastroenterologic Conditions
        "Achalasia",
        "Budd-Chiari Syndrome",
        "Caroli Disease",
        "Congenital Hepatic Fibrosis",
        "Dubin-Johnson Syndrome",
        "Eosinophilic Gastroenteritis",
        "Gastrointestinal Stromal Tumors",
        "Intestinal Leiomyosarcoma",
        "Neonatal Hemochromatosis",
        "OTC Deficiency",
        "Pediatric Caroli Disease",
        "Pediatric Zollinger-Ellison Syndrome",
        "Progressive Familial Intrahepatic Cholestasis",
        "Tropical Sprue",
        "Whipple Disease",
        "Zollinger-Ellison Syndrome",


        # Hematologic Disorders
        "Acquired Hemophilia",
        "Acute Intermittent Porphyria",
        "ALA Dehydratase Deficiency Porphyria",
        "Aplastic Anemia",
        "Bernard-Soulier Syndrome",
        "Chester Porphyria",
        "Donath-Landsteiner Hemolytic Anemia",
        "Evans Syndrome",
        "Factor XI Deficiency",
        "Fanconi Anemia",
        "Glanzmann Thrombasthenia",
        "Hemophilia A",
        "Hemophilia B",
        "Kasabach-Merritt Syndrome",
        "Kikuchi Disease",
        "May-Hegglin Anomaly",
        "Paroxysmal Cold Hemoglobinuria",
        "Paroxysmal Nocturnal Hemoglobinuria",
        "Pediatric Factor VII Deficiency",
        "Pediatric Factor XIII Deficiency",
        "Thrombocytopenia-Absent Radius Syndrome",
        "Waldenstrom Macroglobulinemia",


        # Infectious Diseases
        "Babesiosis",
        "Botulism",
        "Chagas Disease",
        "CNS Whipple Disease",
        "Dermatologic Manifestations of Necrotizing Fasciitis",
        "Dermatologic Manifestations of Nocardiosis",
        "Dermatologic Manifestations of Rubella",
        "Emergency Treatment of Rabies",
        "Fournier Gangrene",
        "HCPS",
        "Hantavirus Pulmonary Syndrome",
        "Herpes Simplex Encephalitis",
        "Leptospirosis",
        "Listeria Infection",
        "Necrotizing Fasciitis",
        "Necrotizing Fasciitis Empiric Therapy",
        "Necrotizing Fasciitis Organism-Specific Therapy",
        "Nocardiosis",
        "Paracoccidioidomycosis",
        "Pediatric Hantavirus Pulmonary Syndrome",
        "Pediatric Nocardiosis",
        "Pediatric Plague",
        "Pediatric Rubella",
        "Pediatric Rubella in Emergency Medicine",
        "Pediatric Yellow Fever",
        "Pinta",
        "Plague",
        "Purpura Fulminans",
        "Q Fever",
        "Rabies",
        "Smallpox",
        "TEN",
        "Tuberculous Meningitis",
        "Variant Creutzfeldt-Jakob Disease and Bovine Spongiform Encephalopathy",
        "Yaws",
        "Yellow Fever",



        # Musculoskeletal Conditions
        "Achondroplasia",
        "Achondroplasia Imaging",
        "Brown-Sequard Syndrome",
        "Diastrophic Dysplasia",
        "Fibrous Dysplasia",
        "Genetics of Achondroplasia",
        "Kugelberg Welander Spinal Muscular Atrophy",
        "Physical Medicine and Rehabilitation for Limb-Girdle Muscular Dystrophy",
        "Spondyloepiphyseal Dysplasia",



        # Neurologic Conditions
        "Acute Disseminated Encephalomyelitis",
        "Adult Optic Neuritis",
        "Brain Imaging in Venous Vascular Malformations",
        "Brain Meningioma",
        "Chronic Inflammatory Demyelinating Polyradiculoneuropathy",
        "Emergent Management of Myasthenia Gravis",
        "Emery-Dreifuss Muscular Dystrophy",
        "Fibromuscular Dysplasia",
        "Guillain-Barre Syndrome",
        "Hereditary Spastic Paraplegia",
        "Huntington Disease",
        "Huntington Disease Dementia",
        "West Syndrome",
        "Krabbe Disease",
        "Lambert-Eaton Myasthenic Syndrome",
        "Lesch-Nyhan Disease",
        "Limb-Girdle Muscular Dystrophy",
        "Medulloblastoma",
        "Medulloblastoma",
        "Medulloblastoma Pathology",
        "Meningioma",
        "Meningiomas Pathology",
        "Methylmalonic Acidemia",
        "Mobius Syndrome",
        "Myasthenia Gravis",
        "Myasthenia Gravis and Pregnancy",
        "Neuroacanthocytosis",
        "Neuroacanthocytosis Syndromes",
        "Neurologic Manifestations of Incontinentia Pigmenti",
        "Ophthalmologic Manifestations of Myasthenia Gravis",
        "Optic Nerve Sheath Meningioma",
        "Pediatric Guillain-Barre Syndrome",
        "Pelizaeus-Merzbacher Disease",
        "Pick Disease",
        "Propionic Acidemia",
        "Schwartz-Jampel Syndrome",
        "Sphenoid Wing Meningioma",
        "Spinal Meningioma Imaging",
        "Tolosa-Hunt Syndrome",
        "Spinal muscular atrophy",



        # Ophthalmologic Conditions
        "AE in Ophthalmology",
        "Benign Essential Blepharospasm",
        "Best Disease",
        "Familial Dysautonomia",
        "Hermansky-Pudlak Syndrome",
        "Kearns-Sayre Syndrome",
        "Marcus Gunn Jaw-winking Syndrome",
        "Vogt-Koyanagi-Harada Disease",
        "von Hippel-Lindau Disease",
        "Von Hippel-Lindau Syndrome Imaging",
        "Wyburn-Mason Syndrome",



        # Pediatric Diseases
        "Achondrogenesis",
        "Aicardi Syndrome",
        "Jeune Syndrome",
        "Bloom Syndrome",
        "Chediak-Higashi Syndrome",
        "CHILD Syndrome",
        "Craniofacial Syndromes",
        "Cystinosis",
        "Dandy-Walker Malformation",
        "Danon Disease",
        "Dermatologic Manifestations of Niemann-Pick Disease",
        "Dermatologic Manifestations of Rubinstein-Taybi Syndrome",
        "Dermatologic Manifestations of Sjogren-Larsson Syndrome",
        "Dermatologic Manifestations of Waardenburg Syndrome",
        "Dracunculiasis",
        "Dyskeratosis Congenita",
        "Ectodermal Dysplasia",
        "Ellis-van Creveld Syndrome",
        "Epidermal Nevus Syndrome",
        "Epidermolytic Ichthyosis",
        "Erythrokeratodermia Variabilis et Progressiva",
        "Fibrodysplasia Ossificans Progressiva",
        "Focal Dermal Hypoplasia Syndrome",
        "Genetics of Rubinstein-Taybi Syndrome",
        "Genetics of Sjogren-Larsson Syndrome",
        "Genetics of Waardenburg Syndrome",
        "Haberland Syndrome",
        "Harlequin Ichthyosis",
        "Incontinentia Pigmenti",
        "West Syndrome",
        "Kernicterus",
        "Lamellar Ichthyosis",
        "LEOPARD Syndrome",
        "Maffucci Syndrome",
        "Treacher Collins Syndrome",
        "Meckel-Gruber Syndrome",
        "Naegeli-Franceschetti-Jadassohn Syndrome",
        "OTC Deficiency",
        "Ovotesticular Disorder of Sexual Development",
        "Pediatric Anti-GBM Disease",
        "Pediatric Factor VII Deficiency",
        "Pediatric Medulloblastoma",
        "Pediatric Severe Combined Immunodeficiency",
        "Refsum Disease",
        "Reye Syndrome",
        "Rickets",
        "Rickets Imaging",
        "Rothmund-Thomson Syndrome",
        "Werner Syndrome",
        "Winchester Syndrome",
        "Wolf-Hirschhorn Syndrome",



        # Rheumatologic Disorders
        "Eosinophilia-Myalgia Syndrome",
        "Eosinophilic Fasciitis",
        "Felty Syndrome",
        "Myositis Ossificans",
        "Relapsing Polychondritis",
        "Systemic Lupus Erythematosus Genetics",



        # Skin and Soft Tissue Conditions
        "Sweet Syndrome",
        "Blue Rubber Bleb Nevus Syndrome",
        "Cutaneous Kikuchi Disease",
        "Degos Disease",
        "Dermatologic Manifestations of Eosinophilia-Myalgia Syndrome",
        "Dermatologic Manifestations of Eosinophilic Fasciitis",
        "Dermatologic Manifestations of Hermansky-Pudlak Syndrome",
        "Dermatologic Manifestations of Stevens-Johnson Syndrome and Toxic Epidermal Necrolysis",
        "Dermatomyositis",
        "Epidermolysis Bullosa",
        "Epidermolysis Bullosa Acquisita",
        "Erythema Multiforme",
        "Darier Disease",
        "Langerhans Cell Histiocytosis",
        "Nephrogenic Systemic Fibrosis",
        "Pachyonychia Congenita",
        "Pediatric Acrodermatitis Enteropathica",
        "Pityriasis Rubra Pilaris",
        "Progressive Lipodystrophy",
        "Netherton Syndrome or Bamboo Hair"


    ]


def main():
    """Função principal"""
    print("\n" + "="*80)
    print("CLINICAL TRIALS DOWNLOADER + TRATAMENTO")
    print("ClinicalTrials.gov - Doenças Raras")
    print("="*80 + "\n")

    # Modo de teste
    TEST_MODE = False  # Mude para True para testar com 5 doenças

    diseases = get_rare_diseases()

    if TEST_MODE:
        diseases = diseases[:5]
        logger.info("⚠ MODO DE TESTE ATIVADO - Processando apenas 5 doenças")

    logger.info(f"Total de doenças a processar: {len(diseases)}")

    # Criar diretório de saída
    output_dir = "clinical_trials_output"
    os.makedirs(output_dir, exist_ok=True)

    # ETAPA 1: Download dos dados
    downloader = ClinicalTrialsDownloader()

    try:
        df = downloader.process_diseases(diseases, save_interval=3)

        if df.empty:
            logger.warning("Nenhum dado foi coletado!")
            return

        # Remover duplicatas
        df_unique = df.drop_duplicates(subset=['NCT Number'], keep='first')

        logger.info(f"\n{'='*80}")
        logger.info("DOWNLOAD CONCLUÍDO!")
        logger.info(f"Total de estudos: {len(df)}")
        logger.info(f"Estudos únicos: {len(df_unique)}")
        logger.info(f"{'='*80}\n")

        # Salvar CSV intermediário
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = os.path.join(output_dir, f"clinical_trials_raw_{timestamp}.csv")
        df_unique.to_csv(csv_file, index=False, encoding='utf-8-sig')
        logger.info(f"✓ Arquivo CSV bruto salvo: {csv_file}\n")

        # ETAPA 2: Tratamento dos dados
        excel_file = f"clinical_trials_treated_{timestamp}.xlsx"
        df_treated = Tratamento(output_dir, excel_file)

        # Estatísticas finais
        logger.info(f"\n{'='*80}")
        logger.info("PROCESSO COMPLETO FINALIZADO!")
        logger.info(f"Arquivo final: {os.path.join(output_dir, excel_file)}")
        logger.info(f"Total de registros tratados: {len(df_treated)}")
        logger.info(f"Estudos no Brasil: {df_treated['Estudo no Brasil'].value_counts().get('SIM', 0)}")
        logger.info(f"{'='*80}\n")

    except Exception as e:
        logger.error(f"Erro fatal: {str(e)}")
        raise


if __name__ == "__main__":
    main()
