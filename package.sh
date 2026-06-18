#!/bin/bash
# Build ConcurrentWitness2Test.zip: a self-contained pyz bundling the
# python sources and pure-python dependencies, plus svcomp.c, docs,
# examples and a start.sh wrapper. Used both locally and by
# .github/actions/create-archive.
set -e
scriptdir=$(cd "$(dirname "$0")" && pwd)
cd "$scriptdir"

rm -rf build ConcurrentWitness2Test ConcurrentWitness2Test.pyz ConcurrentWitness2Test.zip

mkdir build
pip install --target build -r requirements.txt
cp *.py build/
mv build/main.py build/__main__.py
python3 -m zipapp build -o ConcurrentWitness2Test.pyz -p "/usr/bin/env python3"
rm -rf build

mkdir ConcurrentWitness2Test
cp ConcurrentWitness2Test.pyz *.md LICENSE svcomp.c example smoketest.sh ConcurrentWitness2Test/ -r
printf '#!/bin/bash\nscriptdir=$(dirname "$0")\npython3 "$scriptdir"/ConcurrentWitness2Test.pyz "$@"\n' > ConcurrentWitness2Test/start.sh
chmod +x ConcurrentWitness2Test/start.sh ConcurrentWitness2Test/smoketest.sh
zip ConcurrentWitness2Test.zip ConcurrentWitness2Test -r

echo "Created $scriptdir/ConcurrentWitness2Test.zip"
