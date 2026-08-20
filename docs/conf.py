project = 'doc0'
copyright = '2026, Fábio Macêdo Mendes'
author = 'Fábio Macêdo Mendes <fabiomacedomendes@gmail.com>'
extensions = ['sphinx.ext.autodoc', 'sphinx_mdinclude']
templates_path = ['_templates']
exclude_patterns = []
html_theme = 'alabaster'
html_static_path = ['_static']
exclude_patterns = ['_readme.md']
html_theme_options = {
    'navigation_depth': 3,
    'collapse_navigation': False,
    'github_user': 'fabiommendes',
    'github_repo': 'doc0',
}