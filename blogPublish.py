#! /usr/bin/env python
# coding=utf-8

## 用途：上传当前文件夹下的md到博客
## 依赖：pandoc
## 已支持：cnblog、oschina
## 待支持：wordpress、hexo、jekyll、juejin、zhihu、csdn、jianshu
## 环境变量：    
# CNBLOG_USER 账号
# CNBLOG_PASSWORD APPKEY
# OSC_USER 登录账号
# OSC_PASSWORD 登录密码


## 参考：
# https://github.com/nickchen121/cnblogs_automatic_blog_uploading/blob/master/cnblog.py
# https://github.com/dongfanger/pycnblog/blob/master/upload.py
 
import xmlrpc.client as xmlrpclib
import glob
import os
import sys
import json
import time
import datetime
import ssl
import html
import itertools
import markdown
import pypandoc
import re
import argparse

ssl._create_default_https_context = ssl._create_unverified_context

maxTitleNum=99999


## 打开调试日志
Debug = False


def get_folder_hierarchy(file_path):
    folders = []
    path = os.path.dirname(file_path)
    while True:
        path, folder = os.path.split(path)
        if folder:
            folders.append(folder)
        else:
            break
    return folders[::-1]

def get_title(mdpath):
    filename = os.path.basename(mdpath)  # 获取文件名做博客文章标题
    title, _ = os.path.splitext(filename)  # 去除名称后缀
    
    folders = []
    path = os.path.dirname(mdpath)
    while True:
        path, folder = os.path.split(path)
        if folder and folder !='.' :
            folders.append(folder)
        else:
            break
    return title, folders[::-1]

## 处理日期为字符串
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, datetime.date):
            return obj.strftime('%Y-%m-%d')
        else:
            return json.JSONEncoder.default(self, obj)

## oschina必须要修改UA才能用，巨坑
## 此处必须使用支持https的SafeTransport
class CustomTransport(xmlrpclib.SafeTransport):
    def __init__(self):
        super().__init__()
        self.user_agent = "MWeb iOS/1056 CFNetwork/1496.0.7 Darwin/23.5.0"

def exception_handler(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"请求发生错误： {func.__name__}: {e}")
            sys.exit(1)
    return wrapper

class MetaWeblog():
    def __init__(self,url,username,password):
        self.url = url
        self.username = username
        self.password = password
        self.service = xmlrpclib.ServerProxy(uri=url,verbose=Debug, transport=CustomTransport())
        self.blogid = self.getBlogId()
        self.titleIdMap = self.DumpMetaData()

    ''' struct BlogInfo
            string	blogid
            string	url
            string	blogName
    '''
    @exception_handler
    def getBlogId(self):
        BlogInfo = self.service.blogger.getUsersBlogs(self.password, self.username, self.password)
        blogid = BlogInfo[0]["blogid"]
        print(f"")
        print(f"[{self.platform}] 账号信息:")
        print(f'    博客名称: {BlogInfo[0]["blogName"]}')
        print(f'    博客主页: {BlogInfo[0]["url"]}')
        print(f'    博客主ID: {BlogInfo[0]["blogid"]}')
        return blogid

    ''' struct Post
            dateTime	dateCreated - Required when posting.
            string	description - Required when posting.
            string	title - Required when posting.
            array of string	categories (optional)
            struct Enclosure	enclosure (optional)
            string	link (optional)
            string	permalink (optional)
            any	postid (optional)
            struct Source	source (optional)
            string	userid (optional)
            any	mt_allow_comments (optional)
            any	mt_allow_pings (optional)
            any	mt_convert_breaks (optional)
            string	mt_text_more (optional)
            string	mt_excerpt (optional)
            string	mt_keywords (optional)
            string	wp_slug (optional)
    '''
    @exception_handler
    def getRecentPost(self, nums = 10):
        recentPost = self.service.metaWeblog.getRecentPosts(
            self.blogid, self.username, self.password, nums)
        
        # array of struct Post
        return recentPost

    @exception_handler
    def newPost(self, post_files, with_publish = True ):
        newPostId = self.service.metaWeblog.newPost(
            self.blogid, self.username, self.password, post_files, with_publish)
        return newPostId

    @exception_handler
    def editPost(self, postid, post_file, with_publish = True ):
        result = self.service.metaWeblog.editPost(
            postid, self.username, self.password, post_file, with_publish)
        return result

    @exception_handler
    def deletePost(self, postid, with_publish = True ):
        result = self.service.blogger.deletePost(
            self.password, postid, self.username, self.password, with_publish)
        return result

    ''' struct CategoryInfo
        string	description
        string	htmlUrl
        string	rssUrl
        string	title
        string	categoryid
    '''
    @exception_handler
    def getCategories(self):
        CategoryInfoList = self.service.metaWeblog.getCategories(
            self.blogid, self.username, self.password)
        
        # array list of CategoryInfo
        return CategoryInfoList

    ''' struct WpCategory
        string	name
        string	slug (optional)
        integer	parent_id
        string	description (optional)
    '''
    @exception_handler
    def newCategory(self, WpCategory):
        result = self.service.wp.newCategory(
            self.blogid, self.username, self.password, WpCategory)
        return result


    ''' struct fileData
            base64	bits
            string	name
            string	type
        struct urlData
            string	url
    '''
    @exception_handler
    def newMediaObject(self, fileData):
        urlData = self.service.metaWeblog.newMediaObject(
            self.blogid, self.username, self.password, fileData)
        return urlData

    def DownloadArticle(self, path = "./", nums = maxTitleNum):
        """下载文章"""
        recentPost = self.getRecentPost(nums = nums)
        for post in recentPost:
            if "categories" in post.keys():
                if '[随笔分类]unpublished' in post["categories"]:
                    print(post["categories"])

                # 将markdown写入文件
                filepath = path + post["title"] + ".md"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(post["description"])
    
    def DumpMetaData(self, path = "./", nums = maxTitleNum):
        #print(self.service.handlers())
        recentPost = self.getRecentPost(nums = nums)
        titleIdMap = {}
        print(f"文档清单:")
        for post in recentPost:
            if "dateCreated" in post.keys():
                post["dateCreated"] = post["dateCreated"].__str__()
            if "date_created_gmt" in post.keys():
                post["date_created_gmt"] = post["date_created_gmt"].__str__()
            
            titleIdMap[html.unescape(post["title"])] = post["postid"]
            print(f"    文档:{post['title']} 上传时间:{post['dateCreated']}")

        filename = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        filepath = path + filename + ".json"
        # with open(filepath, "w", encoding="utf-8") as f:
        #    json.dump(recentPost, f, indent=4, cls=DateTimeEncoder)
        return titleIdMap

    def post_article(self, mdpath, publish=True):
        title, folders = get_title(mdpath)

        ## 按照markdown格式上传文件必须设置有'[Markdown]'分类,否则无法按照markdown解析
        ## 基于文件夹结构设置多个分类
        defaultCategories = ['[Markdown]']
        folderCategories = ['[随笔分类]'+ cate for cate in folders]
        categories = list(itertools.chain(defaultCategories,folderCategories))

        ## 基于发布标签设置分类
        if not publish:
            categories.append('[随笔分类]待发布') 
        else:
            categories.append('[随笔分类]已发布')

        ## 读取md内容
        description = ''
        with open(mdpath, "r", encoding="utf-8") as f:
            description = f.read()
            description = re.sub(r'\{width="[0-9]+%\}', '', description)

        newpost = dict(
            ## 因为格式原因，转成html效果更好
            ## 转换的效果有待优化
            description = pypandoc.convert_text(description,'html','markdown'), 
            title = title,
            categories = categories,
        )

        if title in self.titleIdMap.keys():
            postId = self.titleIdMap[title]
            return self.editPost(postId, newpost, publish)
        else:
            return self.newPost(newpost, publish)
            
        print(mdfile + " 上传成功")


## cnblog
class CnBlog(MetaWeblog):
    def __init__(self,url,username,password):
        self.platform = "cnblog"
        super().__init__(url,username,password)

## oschina
class OschinaBlog(MetaWeblog):
    def __init__(self,url,username,password):
        self.platform = "oschina"
        super().__init__(url,username,password)


def find_md_files(start_path):
    """
    Recursively find all .md files in the given directory and its subdirectories.
    :param start_path: The path of the directory to start searching from.
    :return: A list of relative paths to the .md files.
    """
    md_files = []
    for root, dirs, files in os.walk(start_path):
        for file in files:
            # 以.md结尾，且不是隐藏文件，且不是以_开头的文件，且非README.md
            if file.endswith('.md') and not file.startswith('.') and not file.startswith('_') and file.upper()!= 'README.MD':
                relative_path = os.path.relpath(os.path.join(root, file), start_path)
                md_files.append(relative_path)
    return md_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Publish blogs to third platforms.')
    
    # 添加文件路径参数
    parser.add_argument('--file', 
                        type=str, 
                        required=False, 
                        help='Path to the file')
    
    parser.add_argument('--dir', 
                        type=str, 
                        required=False, 
                        help='recursive dir')   

    CNBLOG_USER = os.environ.get("CNBLOG_USER")
    CNBLOG_PASSWORD = os.environ.get("CNBLOG_PASSWORD")

    OSC_USER = os.environ.get("OSC_USER")
    OSC_PASSWORD = os.environ.get("OSC_PASSWORD")

    if not CNBLOG_USER and not OSC_USER:
        print("请设置环境变量 CNBLOG_USER 或者 OSC_USER")
        sys.exit(1)

    # 解析命令行参数
    args = parser.parse_args()
    file_path = args.file
    dir_path  = args.dir

    bloggers = []

    if CNBLOG_USER and CNBLOG_PASSWORD:
        cb = CnBlog("https://rpc.cnblogs.com/metaweblog/navyum", CNBLOG_USER, CNBLOG_PASSWORD)
        bloggers.append(cb)

    if OSC_USER and OSC_PASSWORD:
        ob = OschinaBlog("https://my.oschina.net/action/xmlrpc", OSC_USER, OSC_PASSWORD)
        bloggers.append(ob)

    # 循环遍历文件夹，获取所有md
    if dir_path:
        mdfiles = find_md_files(dir_path)
        for mdfile in mdfiles:
            print(f"开始上传本地: {mdfile}")
            for blogger in bloggers:
                #blogger.post_article(mdfile, True)
                print()
    
    if file_path:
        if os.path.exists(file_path) and os.path.splitext(file_path)[1].lower() == '.md':
            print(f"开始上传本地: {file_path}")
            for blogger in bloggers:
                print()
                #blogger.post_article(mdfile, True)
        else:
            print(f"file 对应文件 '{file_path}' 不存在,或者非Markdown文件.")
