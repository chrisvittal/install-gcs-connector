import argparse 
import glob
import logging
import os
from setuptools import setup
from setuptools.command.install import install
import socket
import urllib.request

from pyspark.find_spark_home import _find_spark_home

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO)


GCS_CONNECTOR_URL = 'https://repo1.maven.org/maven2/com/google/cloud/bigdataoss/gcs-connector/hadoop2-1.9.17/gcs-connector-hadoop2-1.9.17-shaded.jar'

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("-k", "--key-file-path", help="Service account key .json")
    args = p.parse_args()
    
    if args.key_file_path:
        if not os.path.isfile(args.key_file_path):
            p.error(f"{args.key_file_path} not found")
    else:
        # look for existing key files in ~/.config. 
        key_file_regexps = [
            "~/.config/gcloud/application_default_credentials.json", 
            "~/.config/gcloud/legacy_credentials/*/adc.json",
        ]
        
        # if more than one file matches a glob pattern, select the newest.
        key_file_sort = lambda file_path: -1 * os.path.getctime(file_path)          
        for key_file_regexp in key_file_regexps:
            paths = sorted(glob.glob(os.path.expanduser(key_file_regexp)), key=key_file_sort)
            if paths:            
                args.key_file_path = next(iter(paths))
                logging.info("Using key file: %s" % args.key_file_path)
                break
        else:
            p.error("No json key files found in these locations: \n%s. Run \n\n  gcloud auth application-default login \n\nThen rerun this script." % (
                ", ".join(key_file_regexps)))
    return args


def is_dataproc_VM():
    """Check if this installation is being executed on a Google Compute Engine dataproc VM"""
    try:
        dataproc_metadata = urllib.request.urlopen("http://metadata.google.internal/0.1/meta-data/attributes/dataproc-bucket").read()
        if dataproc_metadata.decode("UTF-8").startswith("dataproc"):
            return True
    except:
        pass
    return False

    
def main():
    args = parse_args()

    if is_dataproc_VM():
        logging.info("Running on a Dataproc VM. It should already have the GCS cloud connector installed.")
        return  # cloud connector is installed automatically on dataproc VMs 

        
    spark_home = _find_spark_home()

    # download GCS connector jar
    local_jar_path = os.path.join(spark_home, "jars", os.path.basename(GCS_CONNECTOR_URL))
    try:
        logging.info("Downloading %s to %s" % (GCS_CONNECTOR_URL, local_jar_path))
        urllib.request.urlretrieve(GCS_CONNECTOR_URL, local_jar_path)
    except Exception as e:
        logging.error("Unable to download GCS connector to %s. %s" % (local_jar_path, e))
        return

    # update spark-defaults.conf
    spark_config_dir = os.path.join(spark_home, "conf")
    if not os.path.exists(spark_config_dir):
        os.mkdir(spark_config_dir)
    spark_config_file_path = os.path.join(spark_config_dir, "spark-defaults.conf")
    logging.info("Updating json.keyfile to %s in %s" % (args.key_file_path, spark_config_file_path))

    spark_config_lines = [
        "spark.hadoop.google.cloud.auth.service.account.enable true\n",
        "spark.hadoop.google.cloud.auth.service.account.json.keyfile %s\n" % args.key_file_path,
    ]
    try:
        if os.path.isfile(spark_config_file_path):
            with open(spark_config_file_path, "rt") as f:
                for line in f:
                    if "spark.hadoop.google.cloud.auth.service.account.enable" in line:
                        continue
                    if "spark.hadoop.google.cloud.auth.service.account.json.keyfile" in line:
                        continue

                    spark_config_lines.append(line)

        with open(spark_config_file_path, "wt") as f:
            for line in spark_config_lines:
                f.write(line)

    except Exception as e:
        logging.warn("Unable to update spark config %s. %s" % (spark_config_file_path, e))
        return


if __name__ == "__main__":
    main()