import re
import pymongo
import os
import requests
import json
from json import JSONDecodeError
from urllib.parse import urlencode
from hashlib import md5
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
from config import *
from multiprocessing import Pool

client = pymongo.MongoClient(MONGO_URL, _connect=False)
db = client[MONGO_DB]


# 获取索引页
# 获得通过Ajax请求的到的html代码
def get_page_index(offset, keyword):
    data = {
        'offset': offset,
        'format': 'json',
        'keyword': keyword,
        'autoload': 'true',
        'count': 20,
        'cur_tab': 3
    }
    # Ajax请求参数
    url = 'https://www.toutiao.com/search_content/?' + urlencode(data)  # 连接字符串的方法
    try:
        response = requests.get(url)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            return response.text
        return None
    except RequestException:
        print('请求索引页出错')
        return None


# 获取详情页
# 获得图集的url
def parse_page_index(html):
    try:
        data = json.loads(html)
        if data and 'data' in data.keys():
            for item in data.get('data'):
                yield item.get('article_url')  # 通过yield将函数变作一个生成器
    except JSONDecodeError:
        pass


# 获得页面的详细内容
# 判断详情页是否获取成功
def get_page_detail(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        return None
    except RequestException:
        print('请求详情页出错', url)
        return None


# 解析详情页
def parse_page_detail(html, url):
    soup = BeautifulSoup(html, 'lxml')
    title = soup.select('title')[0].get_text()
    images_pattern = re.compile('''gallery: (.*?),
    siblingList''', re.S)  # 此处有修改
    result = re.search(images_pattern, html)
    # 提取'sub_images'里面的数据
    if result:
        data = json.loads(result.group(1))
        if data and 'sub_images' in data.keys():
            sub_images = data.get('sub_images')
            # 遍历 sub_images 里面的url
            images = [item.get('url') for item in sub_images]
            file_paths = []
            for image in images:
                file_path = download_image(image)
                # print(file_path)
                file_paths.append(file_path)
                download_image(image)
            return {
                'title': title,
                'url': url,
                'images': images,
                'file_paths': file_paths
            }


# 存储到mongoDB
def save_to_mongo(result):
    # print(db[MONGO_TABLE])
    if db[MONGO_TABLE].insert(result):
        print('存储到MongoDB成功', result)
        return True
    return False


# 下载详情页图片
def download_image(url):
    print('正在下载', url)
    try:
        response = requests.get(url)
        if response.status_code == 200:
            file_path = '{0}/{1}.{2}'.format(FOLDER, md5(response.content).hexdigest(), 'jpg')
            save_image(response.content, file_path)
            return file_path
    except RequestException:
        print('请求图片出错', url)
        return None


# 图片名
def save_image(content, file_path):
    file_path = file_path
    if not os.path.exists(file_path):
        with open(file_path, 'wb') as f:
            f.write(content)
            f.close()


def main(offset):
    html = get_page_index(offset, KEYWORD)
    for url in parse_page_index(html):
        html = get_page_detail(url)
        if html:
            result = parse_page_detail(html, url)
            if result:
                # print(result)
                save_to_mongo(result)


if __name__ == '__main__':
    # main()
    groups = [x * 20 for x in range(GROUP_START, GROUP_END + 1)]
    pool = Pool()
    pool.map(main, groups)
