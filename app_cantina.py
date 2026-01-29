import streamlit as st
import pytesseract
from PIL import Image
import re
import pandas as pd
from io import BytesIO
import shutil

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema JGE AD14", page_icon="🤪", layout="wide")

# --- CONFIGURAÇÃO INTELIGENTE DO TESSERACT ---
if shutil.which("tesseract"):
    pytesseract.pytesseract.tesseract_cmd = shutil.which("tesseract")
else:
    caminho_windows = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    try:
        pytesseract.pytesseract.tesseract_cmd = caminho_windows
    except:
        st.warning("⚠️ Aviso: Tesseract não encontrado. Se estiver online, ignore.")

# --- FUNÇÕES ---
def converter_mes_para_numero(texto_data):
    meses = {
        'JAN': '01', 'FEV': '02', 'MAR': '03', 'ABR': '04', 'MAI': '05', 'JUN': '06',
        'JUL': '07', 'AGO': '08', 'SET': '09', 'OUT': '10', 'NOV': '11', 'DEZ': '12'
    }
    for mes_nome, mes_num in meses.items():
        if mes_nome in texto_data.upper():
            return texto_data.upper().replace(mes_nome, f"/{mes_num}/").replace(" ", "")
    return texto_data

def extrair_dados(imagem_file, nome_produto, preco_unitario):
    try:
        imagem = Image.open(imagem_file)
        texto = pytesseract.image_to_string(imagem, lang='por')
        linhas = [l.strip() for l in texto.split('\n') if l.strip()]
        
        dados = {
            "Data": "ND",
            "Cliente": "Não identificado",
            "Produto": nome_produto,
            "Valor Total": 0.0,
            "Qtd": 0,
            "Arquivo": imagem_file.name
        }

        # Valor
        match_valor = re.search(r'R\$\s?([\d.,]+)', texto)
        if match_valor:
            valor_texto = match_valor.group(1).replace('.', '').replace(',', '.')
            valor_float = float(valor_texto)
            dados["Valor Total"] = valor_float
            
            if preco_unitario > 0:
                quantidade = valor_float / preco_unitario
                if quantidade.is_integer():
                    dados["Qtd"] = int(quantidade)
                else:
                    dados["Qtd"] = round(quantidade, 2)
            else:
                dados["Qtd"] = 0

        # Data
        match_data = re.search(r'(\d{2})\s([A-Za-z]{3})\s(\d{4})', texto)
        if match_data:
            dados["Data"] = converter_mes_para_numero(match_data.group(0))

        # Cliente
        encontrou_origem = False
        for i, linha in enumerate(linhas):
            if "Origem" in linha:
                encontrou_origem = True
                continue
            if encontrou_origem and "Nome" in linha:
                nome = linha.replace("Nome", "").strip()
                if not nome and (i + 1) < len(linhas):
                    nome = linhas[i+1]
                dados["Cliente"] = nome.title()
                break
        
        return dados
    except Exception as e:
        return {"Erro": str(e), "Arquivo": imagem_file.name}

# --- FUNÇÃO GERADORA DE PDF ---
def gerar_pdf(df, produto, total_val, total_qtd):
    pdf = FPDF()
    pdf.add_page()
    
    # Cabeçalho
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Relatorio de Vendas - {produto}", ln=True, align='C')
    pdf.ln(10)
    
    # Resumo
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Resumo do Dia:", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, f"Faturamento Total: R$ {total_val:.2f}", ln=True)
    pdf.cell(0, 8, f"Quantidade Vendida: {total_qtd} unidades", ln=True)
    pdf.cell(0, 8, f"Total de Comprovantes: {len(df)}", ln=True)
    pdf.ln(10)
    
    # Tabela
    pdf.set_font("Arial", 'B', 10)
    # Cabeçalho da Tabela
    pdf.cell(40, 8, "Data", border=1)
    pdf.cell(70, 8, "Cliente", border=1)
    pdf.cell(20, 8, "Qtd", border=1)
    pdf.cell(30, 8, "Valor", border=1)
    pdf.ln()
    
    # Dados da Tabela
    pdf.set_font("Arial", size=10)
    for index, row in df.iterrows():
        # Tratamento simples para caracteres especiais no PDF (latin-1)
        cliente_limpo = str(row['Cliente']).encode('latin-1', 'replace').decode('latin-1')
        
        pdf.cell(40, 8, str(row['Data']), border=1)
        pdf.cell(70, 8, cliente_limpo[:35], border=1) # Corta nomes muito longos
        pdf.cell(20, 8, str(row['Qtd']), border=1)
        pdf.cell(30, 8, f"R$ {row['Valor Total']:.2f}", border=1)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1')

# --- INTERFACE ---
with st.sidebar:
    st.header("🎯 Configuração do Dia")
    st.info("O que estamos vendendo hoje?")
    
    produto_dia = st.text_input("Nome do Produto", value="Pudim")
    preco_dia = st.number_input("Preço da Unidade (R$)", value=5.00, step=0.50, format="%.2f")
    
    st.write("---")
    st.caption(f"Cálculo: R$ {preco_dia:.2f} = 1 unidade")

st.title(f"📊 Vendas de {produto_dia}")
st.markdown("Arraste os comprovantes Pix para calcular as vendas.")

arquivos = st.file_uploader("Arquivos Pix (PNG, JPG)", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])

if arquivos:
    lista_vendas = []
    barra = st.progress(0)
    
    for i, arq in enumerate(arquivos):
        dados = extrair_dados(arq, produto_dia, preco_dia)
        lista_vendas.append(dados)
        barra.progress((i + 1) / len(arquivos))
    
    df = pd.DataFrame(lista_vendas)
    
    # Organizar colunas
    cols = ["Data", "Cliente", "Produto", "Qtd", "Valor Total", "Arquivo"]
    cols_existentes = [c for c in cols if c in df.columns]
    df = df[cols_existentes]

    # --- TOTAIS ---
    st.success("Leitura concluída!")
    
    if not df.empty and "Valor Total" in df.columns:
        total_reais = df["Valor Total"].sum()
        total_itens = df["Qtd"].sum()
        
        c1, c2 = st.columns(2)
        c1.metric("💰 Faturamento", f"R$ {total_reais:.2f}")
        c2.metric(f"📦 Total de {produto_dia}s", f"{total_itens} un")
        
        st.divider()
        
        st.subheader("📋 Conferência")
        df_final = st.data_editor(df, use_container_width=True)
        
        # --- ÁREA DE DOWNLOADS ---
        col_down1, col_down2 = st.columns(2)
        
        # 1. Download Excel
        def to_excel(df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Vendas')
            return output.getvalue()
        
        with col_down1:
            st.download_button("📥 Baixar Planilha (Excel)", to_excel(df_final), f"Vendas_{produto_dia}.xlsx")

        # 2. Download PDF
        with col_down2:
            try:
                pdf_bytes = gerar_pdf(df_final, produto_dia, total_reais, total_itens)
                st.download_button(
                    label="📄 Baixar Relatório (PDF)",
                    data=pdf_bytes,
                    file_name=f"Relatorio_{produto_dia}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {e}")

    else:
        st.error("Não foi possível ler os valores dos comprovantes.")

elif not arquivos:
    st.info(f"Aguardando arquivos...")