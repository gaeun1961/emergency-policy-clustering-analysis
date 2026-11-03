"""파일 로더와 이름 정규화 (legacy 노트북에서 이동)"""
import re

import pandas as pd


def clean_col_name(col):
    """컬럼 이름 정규화 헬퍼 함수"""
    col = str(col).strip()
    col = col.replace(' ', '')
    col = col.replace('(선별포함)', '')
    col = re.sub(r'[^가-힣A-Za-z0-9]', '', col)
    return col


def clean_sido_name(sido):
    """시도 이름을 '서울', '경기'와 같은 약어 형태로 정규화"""
    sido = str(sido).strip()
    sido = re.sub(r'(광역시|특별시|특별자치시|도|특별자치도)', '', sido, flags=re.UNICODE).strip()
    sido_map = {
        '충청북': '충북', '충청남': '충남', '전라남': '전남', '전라북': '전북',
        '경상북': '경북', '경상남': '경남'
    }
    return sido_map.get(sido, sido)


def load_and_validate_file(file_path, header_candidates, required_cols):
    """
    다양한 인코딩/헤더로 파일을 로드하고 컬럼을 정규화하며 필수 컬럼을 검증하는 함수.
    CSV 또는 Excel 파일을 지원합니다.
    """
    file_path = str(file_path)
    file_type = file_path.split('.')[-1].lower()
    load_func = None
    if file_type == 'csv':
        load_func = pd.read_csv
    elif file_type == 'xlsx':
        load_func = pd.read_excel
    else:
        print(f"Unsupported file type: {file_type} for {file_path}")
        return None

    encodings = ['utf-8', 'euc-kr', 'cp949', None]
    for header_index in header_candidates:
        for enc in encodings:
            try:
                if load_func == pd.read_excel:
                    df = load_func(file_path, header=header_index, engine='openpyxl')
                else:
                    df = load_func(file_path, encoding=enc, header=header_index)

                df.columns = [clean_col_name(col) for col in df.columns.tolist()]

                missing_cols = [col for col in required_cols if col not in df.columns]
                if not missing_cols:
                    print(f"Successfully loaded {file_path} with header {header_index} and encoding {enc}.")
                    return df
                else:
                    print(f"Attempt failed for {file_path} with header {header_index}, encoding {enc}: Missing required columns {missing_cols}")
                    break  # 인코딩은 맞고 헤더 위치가 틀린 경우라 다음 헤더로

            except Exception as e:
                print(f"Attempt failed for {file_path} with header {header_index}, encoding {enc}: {e}")
                continue
    print(f"Failed to load and validate {file_path} after trying all options.")
    return None
