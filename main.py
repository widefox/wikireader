#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

import re
import os
from urlparse import urlparse

try:
    from PyQt5.Qt import (
        QDialog, QGridLayout, QPushButton, QMessageBox, QLabel, QWidget,
        QVBoxLayout, QLineEdit, QIcon, QDialogButtonBox, QTimer, QScrollArea,
        QSize, QFormLayout)
except ImportError:
    from PyQt4.Qt import (
        QDialog, QGridLayout, QPushButton, QMessageBox, QLabel, QWidget,
        QVBoxLayout, QLineEdit, QIcon, QDialogButtonBox, QTimer, QScrollArea,
        QSize, QFormLayout)

# from calibre_plugins.wikipage_ebook.config import prefs
from calibre.utils.config import prefs as cprefs
from calibre.ebooks.conversion.config import load_defaults
from calibre.customize.conversion import OptionRecommendation
from calibre.ptempfile import PersistentTemporaryFile
from calibre.gui2 import Dispatcher, info_dialog

__license__ = 'GPL v3'
__copyright__ = '2011, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

if False:
    # This is here to keep my python error checker from complaining about
    # the builtin functions that will be defined by the plugin loading system
    # You do not need this code in your plugins
    I = get_icons = get_resources = None


class URL(QWidget):

    def __init__(self, parent):
        QWidget.__init__(self, parent)
        self.l = l = QGridLayout()
        self.setLayout(self.l)

        self.label = QLabel('URL:')
        l.addWidget(self.label, 0, 0, 1, 1)
        self.url_edit = QLineEdit(self)
        self.url_edit.setPlaceholderText('Enter the URL of the wikipedia '
                                         'article to download')
        l.addWidget(self.url_edit, 0, 1, 1, 1)

    @property
    def url(self):
        return unicode(self.url_edit.text())


class Title(QWidget):

    def __init__(self, parent):
        QWidget.__init__(self, parent)
        self.ll = ll = QGridLayout()
        self.setLayout(self.ll)

        self.labell = QLabel('Title:')
        ll.addWidget(self.labell, 0, 0, 1, 1)
        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText('Enter a title for the ebook ')
        ll.addWidget(self.title_edit, 0, 1, 1, 1)

    @property
    def title(self):
        return unicode(self.title_edit.text())


def get_recipe(urls, title):
    fmt = cprefs['output_format'].lower()
    pt = PersistentTemporaryFile(suffix='_recipe_out.%s' % fmt.lower())
    pt.close()
    recs = []
    ps = load_defaults('page_setup')
    if 'output_profile' in ps:
        recs.append(('output_profile', ps['output_profile'],
                     OptionRecommendation.HIGH))

    lf = load_defaults('look_and_feel')
    if lf.get('base_font_size', 0.0) != 0.0:
        recs.append(('base_font_size', lf['base_font_size'],
                     OptionRecommendation.HIGH))
        recs.append(('keep_ligatures', lf.get('keep_ligatures', False),
                     OptionRecommendation.HIGH))

    lr = load_defaults('lrf_output')
    if lr.get('header', False):
        recs.append(('header', True, OptionRecommendation.HIGH))
        recs.append(('header_format', '%t', OptionRecommendation.HIGH))

    epub = load_defaults('epub_output')
    if epub.get('epub_flatten', False):
        recs.append(('epub_flatten', True, OptionRecommendation.HIGH))

    recipe = get_resources('wikipedia.recipe')
    url_line = bytes(repr(urls))
    recipe = re.sub(
        br'^(\s+urls = ).+?# REPLACE_ME_URLS', br'\1' + url_line, recipe,
        flags=re.M)
    if title.strip():
        title_line = bytes(repr(title))
        recipe = re.sub(
            br'^(\s+title\s+=\s+)DEFAULT_TITLE', br'\1' + title_line, recipe,
            flags=re.M)
    logo = get_resources('images/icon.png')
    lf = PersistentTemporaryFile('_wiki_logo.png')
    lf.write(logo)
    recipe = recipe.replace(b'LOGO = None', b'LOGO = %r' % lf.name)
    lf.close()
    rf = PersistentTemporaryFile(suffix='_wikipedia.recipe')
    rf.write(recipe)
    rf.close()
    args = [rf.name, pt.name, recs]
    return args, fmt.upper(), [pt, rf, lf]


class DemoDialog(QDialog):

    def __init__(self, gui, icon, do_user_config):
        QDialog.__init__(self, gui)
        self.gui = gui
        self.do_user_config = do_user_config

        self.db = gui.current_db

        self.l = QVBoxLayout()
        self.setLayout(self.l)

        self.setWindowTitle('Wiki Reader')
        self.setWindowIcon(icon)

        self.helpl = QLabel(
            'Enter the URL of a wikipedia article below. '
            'It will be downloaded and converted into an ebook.')
        self.helpl.setWordWrap(True)
        self.l.addWidget(self.helpl)

        self.w = QWidget(self)
        self.sa = QScrollArea(self)
        self.l.addWidget(self.sa)
        self.w.l = QVBoxLayout()
        self.w.setLayout(self.w.l)
        self.sa.setWidget(self.w)
        self.sa.setWidgetResizable(True)

        self.title = Title(self)
        self.w.l.addWidget(self.title)

        self.urls = [URL(self)]
        self.w.l.addWidget(self.urls[0])

        self.add_more_button = QPushButton(
            QIcon(I('plus.png')), 'Add another URL')
        self.l.addWidget(self.add_more_button)

        self.bb = QDialogButtonBox(self)
        self.bb.setStandardButtons(self.bb.Ok | self.bb.Cancel)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        self.l.addWidget(self.bb)
        self.book_button = b = self.bb.addButton(
            'Convert a Wiki&Book', self.bb.ActionRole)
        b.clicked.connect(self.wiki_book)

        self.add_more_button.clicked.connect(self.add_more)
        self.finished.connect(self.download)

        self.setMinimumWidth(500)
        self.resize(self.sizeHint())
        self.single_url = None

    def wiki_book(self):
        d = QDialog(self)
        d.l = l = QFormLayout(d)
        l.setFieldGrowthPolicy(l.ExpandingFieldsGrow)
        d.setWindowTitle('Enter WikiBook URL')
        d.la = la = QLabel(
            '<p>You can convert a pre-made WikiBook into a book here. '
            'Simply enter the URL to the WikiBook page. For a list of '
            'WikiBooks, see '
            '<a href="https://en.wikipedia.org/wiki/Special:PrefixIndex/Book:'
            '">here</a>.'
        )
        la.setMinimumWidth(400)
        la.setWordWrap(True)
        la.setOpenExternalLinks(True)
        l.addRow(la)
        d.le = le = QLineEdit(self)
        l.addRow('WikiBook &URL:', le)
        le.setText('https://')
        le.selectAll()
        d.bb = bb = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, d)
        l.addRow(bb)
        bb.accepted.connect(d.accept), bb.rejected.connect(d.reject)
        if d.exec_() == d.Accepted:
            self.single_url = le.text()
            self.accept()

    def do_resize(self):
        a = self.sizeHint()
        b = self.w.sizeHint()
        h = min(400, b.height())
        self.resize(QSize(a.width(), h + 200))

    def scroll_to_bottom(self):
        v = self.sa.verticalScrollBar()
        v.setValue(v.maximum())

    def add_more(self):
        url = URL(self)
        self.urls.append(url)
        self.w.l.addWidget(url)
        QTimer.singleShot(0, self.do_resize)
        QTimer.singleShot(10, self.scroll_to_bottom)

    def about(self):
        # Get the about text from a file inside the plugin zip file
        # The get_resources function is a builtin function defined for all your
        # plugin code. It loads files from the plugin zip file. It returns
        # the bytes from the specified file.
        #
        # Note that if you are loading more than one file, for performance, you
        # should pass a list of names to get_resources. In this case,
        # get_resources will return a dictionary mapping names to bytes. Names
        # that are not found in the zip file will not be in the returned
        # dictionary.
        text = get_resources('about.txt')
        QMessageBox.about(self, 'About the Wiki Reader', text.decode('utf-8'))

    # def config(self):
    #     self.do_user_config(parent=self)
    # Apply the changes
    #     self.label.setText(prefs['hello_world_msg'])

    def download(self, retcode):
        if retcode != self.Accepted:
            return
        if self.single_url is None:
            urls = [x.url for x in self.urls]
            urls = [x.strip() for x in urls if x.strip()]
            urls = [
                ('http://' + x) if not urlparse(x).scheme else x for x in urls]
        else:
            urls = self.single_url
            self.single_url = None
        args, fmt, temp_files = get_recipe(urls, self.title.title)
        job = self.gui.job_manager.run_job(
            Dispatcher(self.fetched), 'gui_convert', args=args,
            description='Fetch article from Wikipedia')
        job.extra_conversion_args = (temp_files, fmt)
        # don't prompt if all OK
        # if isinstance(urls, list):
        #     info_dialog(
        #         self, 'Downloading',
        #         'Downloading %d article(s) from Wikipedia. When the download'
        #         ' completes the book will be added to your calibre library.'
        #         % len(urls), show=True, show_copy_button=False)
        # else:
        #     info_dialog(
        #         self, 'Downloading',
        #         'Downloading book from Wikipedia. When the download'
        #         ' completes the book will be added to your calibre library.',
        #         show=True, show_copy_button=False)

    def fetched(self, job):
        if job.failed:
            return self.gui.job_exception(job)
        temp_files, fmt = job.extra_conversion_args
        fname = temp_files[0].name
        self.gui.iactions['Add Books']._add_books([fname], False)
        for f in temp_files[1:]:
            try:
                os.remove(f.name)
            except:
                pass
        # don't prompt if all OK
        # self.gui.status_bar.show_message('Wikipedia articles fetched.', 3000)
