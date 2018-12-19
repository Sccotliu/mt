# coding=UTF-8
import logging
import os
import re
import requests
import sys
import traceback
import uuid

language_dict = {
    "fr": "fr-FR",
    "de": "de-DE",
    "es": "es-ES",
    "ko": "ko-KR",
    "zh-TW": "zh-TW",
    "it": "it-IT",
    "pl": "pl-PL",
    "ru": "ru-RU",
    "tr": "tr-TR",
    "pt": "pt-BR"
}


def get_args():
    try:
        tlang_code = sys.argv[1]
        input_folder = sys.argv[2]
        if (tlang_code is None or tlang_code == '') or (input_folder is None or input_folder == ''):
            raise Exception
    except:
        print("########################## ERROR TIP ###############################\n"
              "## Usage: python3 cleanData.py {tlang_code} {input_folder}        ##\n"
              "## Note: is_detect_lang is mixed language handle switch (boolean) ##\n"
              "####################################################################\n")
    return tlang_code, input_folder


def pre_handle(line):
    line = line.strip(' ')
    line = line.replace("&amp;", "&").replace("&amp;", "&").replace("&nbsp;", ' ').replace("&quot;", '"').replace(
        '&lt;', '<').replace('&gt;', '>').replace("&#xD;", " ").replace("\t", "")
    return line


def del_blank(s):
    return " ".join([x for x in s.split(" ") if x != ""])


def is_significant(s):
    # 'o\n'这类单字母可以认为是无效行
    return s != '' and s != '\n' and len(s) > 2


def ms_detect_lang_init():
    global constructed_url, headers
    if 'TRANSLATOR_TEXT_KEY' in os.environ:
        subscription_key = os.environ['TRANSLATOR_TEXT_KEY']
    else:
        print('Environment variable for TRANSLATOR_TEXT_KEY is not set.')
        exit()

    base_url = 'https://api.cognitive.microsofttranslator.com'
    path = '/detect?api-version=3.0'
    constructed_url = base_url + path

    headers = {
        'Ocp-Apim-Subscription-Key': subscription_key,
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }


def mixed_language_handle(start_index, src_texts, tlines, valid_sfile, valid_tfile):
    """
    混语言处理（剔除混语言，将有效平行语句分别写入vaildLang_xx.align）

    关键点：利用list的有序性。src_texts 和 response 都是 list，理论上第i个text对应了第i个res_item
    :return:
    """
    body = [{'text': text} for text in src_texts]
    try:
        request = requests.post(constructed_url, headers=headers, json=body)
        response = request.json()
        for i in range(len(response)):
            # fetch all possible lang for every res_item
            langs = []
            langs.append(response[i]['language'])
            if response[i].get('alternatives', None):
                for item in response[i]['alternatives']:
                    langs.append(item['language'])
            # if has 'en', write valid file
            if 'en' in langs:
                text_index = start_index + i
                valid_sfile.write(src_texts[i])
                valid_tfile.write(tlines[text_index])
    except Exception as e:
        print('detect lang raise exception, the texts is: %s' % src_texts)
        logging.exception(traceback.format_exc())


def content_handle(content_line):
    content = seg_tag_pattern.sub('', content_line)
    content = html_pattern.sub('', content)
    content = tr_pattern.sub('', content)
    content = html_tag_pattern.sub('', content)
    content = http_pattern.sub("", content)
    content = del_blank(content)
    return content


def init_file_path_list(root_dir):
    for lists in os.listdir(root_dir):
        path = os.path.join(root_dir, lists)
        file_path_list.append(path)
        if os.path.isdir(path):
            init_file_path_list(path)


def file_output_prepare(paths):
    files = []
    for path in paths:
        if os.path.exists(path):
            os.remove(path)
        files.append(open(path, 'a', encoding='utf-8'))
    return files


def count_align_check(source_write_count, target_write_count, file_path):
    if source_write_count != target_write_count:
        print("ERROR: {} parse error: write count no align, please check parse rule".format(file_path))
        sys.exit(0)


def small_file_clean_data(file_path, sfile, tfile):
    """
    小文件逐行处理
    :return:
    """
    try:
        f = open(file_path, 'r', encoding='utf-8')
        lines_origin = f.readlines()
    except:
        f = open(file_path, 'r', encoding='utf-16')
        lines_origin = f.readlines()
    lines = list(map(pre_handle, lines_origin))
    source_write_count = 0
    target_write_count = 0
    source_content = ''
    target_content = ''
    for i in range(0, len(lines)):
        line = lines[i]
        if skip_file_pattern.match(line):
            break
        if source_pattern.match(line):
            source_line = lines[i + 1]
            source_content = content_handle(source_line)
        if target_pattern.match(line) and is_significant(source_content):
            target_line = lines[i + 1]
            target_content = content_handle(target_line)
        # 当本轮解析的st/tt同时有效时，写入
        if is_significant(source_content) and is_significant(target_content):
            sfile.write(source_content)
            source_write_count += 1
            tfile.write(target_content)
            target_write_count += 1
            # 清理本轮数据
            source_content = ''
            target_content = ''
    f.close()
    count_align_check(source_write_count, target_write_count, file_path)


def small_file_detect_lang(sfile, tfile, valid_sfile, valid_tfile):
    """
    小文件混语言处理（批量）
    :return:
    """
    slines = sfile.readlines()
    flines = tfile.readlines()
    src_texts = []
    start_index = -100
    for i in range(0, len(slines)):
        src_texts.append(slines[i])
        # 每100条(max) | row_end 处理一次混语言
        if i % 100 == 99 or i == len(slines)-1:
            start_index += 100
            mixed_language_handle(start_index, src_texts, flines, valid_sfile, valid_tfile)
            src_texts.clear()
            print("current detect progress: %s" % ("%.2f%%" % ((i+1) / len(slines) * 100)))


# input params
tlang_code, input_folder = get_args()
# tlang_code = 'tr'
# input_folder = '/Users/caius_kong/Documents/work/2018/MT/TMX/tr-TR/2018.12'
is_detect_lang = False

# match pattern
source_pattern = re.compile(r'<tuv xml:lang="EN-US">', re.IGNORECASE)
target_pattern_str = r'<tuv xml:lang="{}">'.format(language_dict.get(tlang_code))
target_pattern = re.compile(target_pattern_str, re.IGNORECASE)
skip_file_pattern = re.compile(r'<prop type="RTFFontTable">')
seg_tag_pattern = re.compile(r'<[/]?seg>')
html_tag_pattern = re.compile(r'</?\w+[^>]*>')
html_pattern = re.compile(r'<!DOCTYPE html>[\W\w]*</html>', re.IGNORECASE)
tr_pattern = re.compile(r'<tr[^>]*>[\W\w]*<[/]?tr[^>]*>')
# css_pattern =  re.compile(r'[\W\w]*{[\W\w]*}')
http_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

file_path_list = []
init_file_path_list(input_folder)
output_folder = os.path.join(os.getcwd(), "output")
sfile_path = output_folder + "/all_en.align"
tfile_path = output_folder + "/all_" + tlang_code + ".align"
sfile, tfile = file_output_prepare((sfile_path, tfile_path))
count = 0
for file_path in file_path_list:
    count += 1.0
    if os.path.splitext(file_path)[1] != '.tmx':
        continue
    print("file parse: " + file_path)
    small_file_clean_data(file_path, sfile, tfile)
    print("current progress: %s" % ("%.2f%%" % (count/len(file_path_list)*100)))
sfile.close()
tfile.close()

# 混语言处理
if is_detect_lang:
    print('\nstart detect lang...')
    ms_detect_lang_init()

    valid_sfile_path = output_folder + "/vaildLang_en.align"
    valid_tfile_path = output_folder + "/vaildLang_" + tlang_code + ".align"
    sfile = open(sfile_path, 'r', encoding='utf-8')
    tfile = open(tfile_path, 'r', encoding='utf-8')
    valid_sfile, valid_tfile = file_output_prepare((valid_sfile_path, valid_tfile_path))
    small_file_detect_lang(sfile, tfile, valid_sfile, valid_tfile)

    sfile.close()
    tfile.close()
    valid_sfile.close()
    valid_tfile.close()
