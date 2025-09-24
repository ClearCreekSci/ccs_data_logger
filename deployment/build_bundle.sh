VERSION="NotForRelease"
PREFIX="WeatherDataLogger_Install_Bundle"

if [ $# -eq 1 ]; then
    VERSION="$1"
fi

./make_manifest.sh $VERSION > ./manifest.xml

zip -r "${PREFIX}_version_${VERSION}.zip" ./manifest.xml ../data_logger.py ../requirements.txt ../plugins/*.py ../system/ccsweatherdatalogger.service





