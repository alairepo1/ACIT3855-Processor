import datetime
import json
import logging
import logging.config
import os

import connexion
import requests
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from connexion import NoContent
from flask_cors import CORS, cross_origin

with open('log_conf.yaml', 'r') as f:
    """loads the configuration for logging"""
    log_config = yaml.safe_load(f.read())
    logging.config.dictConfig(log_config)

try:
    with open('~/deploy/ACIT3855-deployment/configs/processor/app_conf.yml', 'r') as f:
        app_config = yaml.safe_load(f.read())
except FileNotFoundError:
    with open('app_conf.yml', 'r') as f:
        app_config = yaml.safe_load(f.read())

def init_scheduler():
    """
    Sets the logger to run at an interval
    config is set in the app_config.yaml
    """
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(populate_stats,
                  'interval',
                  seconds=app_config['scheduler']['period_sec'])
    sched.start()


# Functions
def get_form_stats():
    """ This method gets the contents of the data.json and returns contents and status code"""
    logger.info("Start get_form_stats request.")
    try:
        if os.path.exists(app_config['datastore']['filename']):
            with open(app_config['datastore']['filename'], "r+") as f:
                string_data = f.read()
                data = json.loads(string_data)

                last_data = data[-1]

                logger.debug("Form data: {}".format(data))
                logger.info("Request complete.")
                return last_data, 200
        else:
            raise FileNotFoundError("File not found")
    except FileNotFoundError as e:
        logger.error(e)
        return 404


def populate_stats():
    """
    populates the data.json log file. Creates a new file if it does
    not exist.

    Logger will log the stats of forms recieved since the last
    time the logger was called.
    """
    logger.info("Start Periodic Processing.")

    # Checks if the data.json file exists
    if os.path.exists(app_config['datastore']['filename']):
        # Opens the data.json file as read-write
        with open(app_config['datastore']['filename'], "r+") as f:

            # Read the data as string and loads it as a dictionary.
            string_data = f.read()
            log_data = json.loads(string_data)

            # Gets the date of the last object written in the data.json
            last_date = log_data[-1]['dateoflog']
            date_now = datetime.datetime.strftime(
                datetime.datetime.now(), "%Y-%m-%dT%H:%M:%S")

            # API request data from port 8090 (lab2) with
            # date of last object and current date
            # the data will return as a json object
            headers = {
                "Content-Type": "application/json"
            }

            PARAMS = {"startDate": last_date,
                      "endDate": date_now}
            repair = requests.get(app_config['eventstore']['url'] + '/repairRequest',
                                  params=PARAMS, headers=headers)

            orders = requests.get(app_config['eventstore']['url'] + '/orders',
                                  params=PARAMS, headers=headers)

            response_repair = json.loads(repair.content)
            response_orders = json.loads(orders.content)

            # Checks status code for errors and logs if any.
            # Then preceeds to calculate stats from the request
            # data and old data
            if repair.status_code != 200 and orders.status_code != 200:
                logger.error("Error {}".format(response_repair.status_code))
                logger.info("Period processing ended")
            else:

                new_stats_repair = len(response_repair)
                new_stats_order = len(response_orders)

                if new_stats_repair > 0:
                    logger.info(
                        "{} of repairs recieved".format(new_stats_repair))

                    repair_msg = "{} of forms recieved. since {}.".format(
                        new_stats_repair,
                        last_date)
                    logger.debug(repair_msg)
                else:
                    repair_msg = "no new items"

                if new_stats_order > 0:
                    logger.info(
                        "{} of orders recieved".format(new_stats_order))
                    order_msg = "{} new items added to orders since {}.".format(
                        new_stats_order, last_date)
                    logger.debug(order_msg)

                else:
                    order_msg = "no new orders"

                if new_stats_order == 0 and new_stats_repair == 0:
                    logger.info("Period processing ended")
                else:
                    new_data = {
                        "dateoflog": date_now,
                        "num_orders": new_stats_order,
                        "num_repair": new_stats_repair,
                        "order_stats": order_msg,
                        "repair_stats": repair_msg
                    }

                    """line 107 will shallow copy existing data"""
                    new_log = []
                    
                    new_log.append(log_data[-1])
                    new_log.append(new_data)
                    f.seek(0)
                    f.write(json.dumps(new_log, sort_keys=True, indent=4))
                    f.truncate()
                    f.close()

                logger.info("Period processing ended")

    else:
        # Creates the data.json file when it does not exist.
        date = datetime.datetime.now()
        default_data = [
            {
                "dateoflog": datetime.datetime.strftime(date, "%Y-%m-%dT%H:%M:%S"),
                "num_orders": 0,
                "num_repair_orders": 0
            }
        ]
        with open(app_config['datastore']['filename'], "w") as data:
            data.write(json.dumps(default_data,
                                  sort_keys=True,
                                  indent=4)
                       )
            data.close()
            logger.info("Period processing ended")


app = connexion.FlaskApp(__name__, specification_dir='')
CORS(app.app)
app.app.config['CORS_HEADERS'] = 'Content-Type'
app.add_api("openapi.yaml")

if __name__ == "__main__":
    init_scheduler()
    app.run(port=8100, use_reloader=False)
