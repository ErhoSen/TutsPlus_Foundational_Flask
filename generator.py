from flask import Flask, render_template, url_for, abort, request
from flask.ext.frozen import Freezer
from werkzeug.utils import cached_property
from werkzeug.contrib.atom import AtomFeed

import markdown
import yaml
import boto
from boto.s3.key import Key

import os
import sys
import collections

DOMAIN = "http://domain.com"
AWS_ACCESS_KEY_ID = 'SECRETSECRETSECRET'
AWS_SECRET_ACCESS_KEY = 'secret'
FREEZER_BASE_URL = 'http://github_username.github.io'
FREEZER_DESTINATION_IGNORE = ['.git*', 'projects', 'README.MD']
POSTS_FILE_EXTENSION = '.md'
POSTS_HOME_DIR = 'posts'


class SortedDict(collections.MutableMapping):

    def __init__(self, items=None, key=None, reverse=False):
        self._items = {}
        self._keys = []
        if key:
            self._key_fn = lambda k: key(self._items[k])
        else:
            self._key_fn = lambda k: self._items[k]
        self._reverse = reverse

        if items is not None:
            self.update(items)

    def __getitem__(self, key):
        return self._items[key]

    def __setitem__(self, key, value):
        self._items[key] = value
        if key not in self._keys:
            self._keys.append(key)
            self._keys.sort(key=self._key_fn, reverse=self._reverse)

    def __delitem__(self, key):
        self._items.pop(key)
        self._keys.remove(key)

    def __iter__(self):
        for key in self._keys:
            yield key

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self._items)

    def __len__(self):
        return len(self._keys)


class Post(object):

    def __init__(self, post_name, ext='.md'):
        self.urlpath = post_name
        self.filepath = os.path.join(POSTS_HOME_DIR, post_name+ext)
        self.published = False
        self._initialize_metadata()

    @cached_property
    def html(self):
        with open(self.filepath, 'r') as fin:
            content = fin.read().split('\n\n', 1)[1].strip()
        return markdown.markdown(content, extensions=['extra', 'codehilite'])

    def url(self, _external=False):
        return url_for('post', path=self.urlpath, _external=_external)

    def _initialize_metadata(self):
        content = ""
        with open(self.filepath, 'r') as fin:
            for line in fin:
                if not line.strip():
                    break
                content += line
        self.__dict__.update(yaml.load(content))


class Blog(object):

    def __init__(self, app, root_dir='', file_ext=None):
        self.root_dir = root_dir
        self.file_ext = file_ext if file_ext is not None else app.config['POSTS_FILE_EXTENSION']
        self._app = app
        self._cache = SortedDict(key=lambda p: p.date, reverse=True)
        self._initialize_cache()

    @property
    def posts(self):
        if self._app.config['DEBUG']:
            return self._cache.values()
        else:
            return [post for post in self._cache.values() if post.published]

    def get_post_or_404(self, path):
        """
        :return: the Post object for the given :param path: or raises a NotFound exception
        """
        try:
            return self._cache[path]
        except KeyError:
            abort(404)

    def _initialize_cache(self):
        """
            Walks the posts directory and adds all files to the cache
        """
        for (root, dirpaths, filepaths) in os.walk(self.root_dir):
            for filepath in filepaths:
                filename, ext = os.path.splitext(filepath)
                if ext == self.file_ext:
                    post = Post(filename, ext=ext)
                    self._cache[post.urlpath] = post

app = Flask(__name__)  # name current file
app.config.from_object(__name__)
blog = Blog(app, root_dir='posts')
freezer = Freezer(app)


@app.template_filter('date')
def format_date(value, format="%B %d, %Y"):
    return value.strftime(format)


@app.route("/")
def index():
    return render_template('index.html', posts=blog.posts)


@app.route('/blog/<path:path>/')
def post(path):
    #import ipdb; ipdb.set_trace() # TODO: Remove. This line for test case only.
    post = blog.get_post_or_404(path)
    return render_template('post.html', post=post)

@app.route('/projects/<path:path>/')
def project(path):
    #import ipdb; ipdb.set_trace() # TODO: Remove. This line for test case only.
    print path
    return render_template(path+"/index.html", title = 'Projects')

@app.route('/feed.atom')
def feed():
    feed = AtomFeed('Recent Articles',
                    feed_url=request.url,
                    url=request.url_root)
    posts = blog.posts[:10]
    title = lambda p: '%s: %s' % (p.title, p.subtitle) if hasattr(p, 'subtitle') else p.title
    for post in posts:
        feed.add(title(post),
                 unicode(post.html),
                 content_type='html',
                 author="Author Name",
                 url=post.url(_external=True),
                 updated=post.date,
                 published=post.date)
    return feed.get_response()

def deploy(root_dir):
    conn = boto.connect_s3(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    bucket = conn.get_bucket(DOMAIN)
    for (root, dirpaths, filepaths) in os.walk(root_dir):
        for filepath in filepaths:
            filename = os.path.join(root, filepath)
            name = filename.replace(root_dir, '', 1)[1:]
            key = Key(bucket, name)
            key.set_contents_from_filename(filename)

    print 'Site is now up on %s' % bucket.get_website_endpoint()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'build':
        freezer.freeze()
    elif len(sys.argv) > 1 and sys.argv[1] == 'deploy':
        freezer.freeze()
        deploy('build')
    else:
        post_files = [post.filepath for post in blog.posts]
        app.run(port=8000, debug=True, extra_files=post_files)