"""이름 정규화 (legacy 노트북에서 이동)"""
import re


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
