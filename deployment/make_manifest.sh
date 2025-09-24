TIME=`date`
COMMIT=`git rev-parse HEAD`

echo "<manifest>"
echo "<time>$TIME</time>"
echo "<commit>$COMMIT</commit>"
if [ $# -eq 1 ]; then
    VERSION="$1"
echo "<version>$VERSION</version>"
fi
if [ -f manifest_additions.xml ]; then
    cat manifest_additions.xml
fi
echo "</manifest>"

