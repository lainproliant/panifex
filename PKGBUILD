pkgbase='python-panifex'
pkgname=('python-panifex')
_module='panifex'
pkgver='0.3'
pkgrel=1
pkgdesc="A make-like DI-based Python build system."
url="https://github.com/lainproliant/panifex"
depends=('python')
makedepends=('python-setuptools')
license=('MIT')
arch=('any')
source=("https://files.pythonhosted.org/packages/source/${_module::1}/$_module/$_module-$pkgver.tar.gz")
sha256sums=('36976cc5a41c88d38fba470c22439f6ad499816822d3f7a385e97a49b79bbb53')

build() {
    cd "${srcdir}/${_module}-${pkgver}"
    python setup.py clean --all
    python setup.py build
}

package() {
    depends+=()
    cd "${srcdir}/${_module}-${pkgver}"
    python setup.py install --root="${pkgdir}" --optimize=1 --skip-build
    install -Dm644 "$srcdir/${_module}-${pkgver}/LICENSE" "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
}
