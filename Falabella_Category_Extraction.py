from concurrent.futures import as_completed, ThreadPoolExecutor
from datetime import datetime, timedelta
from json import JSONDecodeError
from logging import (
    Formatter,
    getLogger,
    FileHandler,
    INFO,
    shutdown,
    StreamHandler,
)
from os import makedirs, path
from re import search, sub
from sys import stdout
from time import localtime, strftime, time
from traceback import TracebackException

from openpyxl import load_workbook, Workbook
from pandas import concat, DataFrame, read_csv
from requests import get
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException
from seleniumwire.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from urllib.parse import quote_plus
from webdriver_manager.chrome import ChromeDriverManager

CURRENT_DATE = datetime.now().date()
URL_FALABELLA = "https://www.falabella.com.pe/falabella-pe"
DATA_FILENAME = "falabella_category"
DATA_FOLDER = "Data"
TIME_FILENAME = "Tiempos.xlsx"
TIME_SHEET_NAME = "Categorias"
# Diccionario de las categorías
DATA_DICT_FILENAME = "category_dictionary.csv"
DATA_DICT_HEADERS = ["Link_subcat", "Name", "Link_cat"]

# Variables para manejar la api
API_HEADERS = {
    "accept": "*/*",
    "accept-language": "es,es-ES;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "content-type": "application/json",
    "sec-ch-ua": '"Chromium";v="110", "Not A(Brand";v="24", "Microsoft Edge";v="110"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-device-type": "desktop",
    "Referer": "https://www.falabella.com.pe/",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}
API_URL = "https://www.falabella.com.pe/s/browse/v1/listing/pe"
API_PARAMS = {
    "page": "1",
    "categoryId": None,
    "categoryName": None,
    "pgid": "2",
    "pid": "799c102f-9b4c-44be-a421-23e366a63b82",
    "zones": "912_LIMA_2,OLVAA_81,LIMA_URB1_DIRECTO,URBANO_83,IBIS_19,912_LIMA_1,150101,PERF_TEST,150000",
}
THREAD = ThreadPoolExecutor()
LOGGER = getLogger(__name__)


class Tiempo:
    """Representa el tiempo de ejecución del scraper

    Attributes:
        start_time (float): Hora de inicio de la ejecución del scraper en segundos
        execution_date (str): Fecha de extracción de las categorias en formato %d/%m/%Y
        start_hour (str): Hora de inicio de la ejecución del scraper en formato %H:%M:%S
        end_hour (str): Hora de término de la ejecución del scraper en formato %H:%M:%S
        quantity (int): Cantidad de categorías extraídas de la página de saga falabella
        time_execution (str): Tiempo de ejecución del scraper en formato %d days, %H:%M:%S
        category_per_min (float): Cantidad de categorías que puede extraer el scraper en un minuto
        num_errors (int): Cantidad de errores ocurridos durante la ejecución del scraper
    """

    def __init__(self):
        """Genera todos los atributos para una instancia de la clase Tiempo"""
        self._start_time = time()
        self._execution_date = CURRENT_DATE.strftime("%d/%m/%Y")
        self._start_hour = strftime("%H:%M:%S", localtime(self._start_time))
        self._end_hour = None
        self._quantity = 0
        self._time_execution = None
        self._category_per_min = None
        self._num_errors = 0
        LOGGER.info(f"Hora de inicio: {self._start_hour}")

    @property
    def execution_date(self):
        """Retorna el valor actual del atributo fecha"""
        return self._execution_date

    @property
    def num_errors(self):
        """Retorna el valor actual o actualiza el valor del atributo num_error"""
        return self._num_errors

    @property
    def quantity(self):
        """Retorna el valor actual o actualiza el valor del atributo cantidad"""
        return self._quantity

    @quantity.setter
    def num_errors(self, num_errors):
        self._num_errors = num_errors

    @quantity.setter
    def quantity(self, quantity):
        self._quantity = quantity

    def set_param_final(self):
        """Registra los parámetros finales de la medición del tiempo de ejecución del scraper"""
        end = time()
        self._end_hour = strftime("%H:%M:%S", localtime(end))
        total = end - self._start_time
        self._time_execution = str(timedelta(seconds=total)).split(".")[0]
        self._category_per_min = round(self._quantity / (total / 60), 2)
        LOGGER.info(f"Se halló {self._num_errors} errores")
        LOGGER.info(f"Categorías Extraídas: {self._quantity}")
        LOGGER.info(f"Hora Fin: {self._end_hour}")


class Error:
    """Representa a un error ocurrido durante la ejecución de un scraper

    Attributes:
        code_error (str): Parte del código donde se origina el error
        message (str): Mensaje del error
        line_error (int): Linea del código donde ocurre el error
        type (type): Tipo de error
    """

    def __init__(self, error):
        """Genera todos los atributos para una instancia de la clase Error

        Args:
            error (Exception): Error ocurrido durante la ejecución del scraper
        """
        traceback_error = TracebackException.from_exception(error)
        error_stack = traceback_error.stack[0]
        self._code_error = error_stack.line
        self._line_error = error_stack.lineno
        self._message = traceback_error._str
        self._type = traceback_error.exc_type

    def imprimir_error(self):
        """Imprime toda la información del error por consola"""
        LOGGER.error("Ha ocurrido un error:")
        LOGGER.error(f"Clase: {self._type}")
        LOGGER.error(f"Mensaje: {self._message}")
        LOGGER.error(f"Línea de error: {self._line_error}")
        LOGGER.error(f"Codigo de error: {self._code_error}")


class Data(DataFrame):
    """Representa al conjunto de datos generado por el scraper"""

    def __init__(self, data):
        """Genera todos los atributos para una instancia de la clase Data

        Args:
            data (pandas.core.frame.DataFrame or dict): Contiene la información de las categorías
        """
        super().__init__(data=data)

    def concat_dataset(self, dataset_to_concat, axis=0):
        """Agrega filas o columnas provenientes de un dataframe al dataset actual

        Args:
            dataset_to_concat (pandas.core.frame.DataFrame): Dataset con el que se va a combinar
            axis (int, optional): Indica si se va agregar columnas o filas al dataset. Defaults to 0.
        """
        self = concat([self, dataset_to_concat], axis=axis)

    def find_rows(self, column_name, value=""):
        """Buscar todas las filas que coincidan con el criterio de búsqueda

        Args:
            column_name (str): Columna donde se va a realizar la búsqueda
            value (str): Valor a buscar

        Returns:
            list: Lista de registros que coinciden con el criterio de búsqueda
        """
        return self[self[column_name] == value].values.tolist()

    def get_column_values(self, column_name):
        """Retorna una lista de valores de una o varias columna(s) existente(s) en el dataset

        Args:
            column_name (str or list): Nombre o lista de nombres de la(s) columna(s)

        Returns
            list: Lista de valores
        """
        return self[column_name].values.tolist()

    def length(self):
        """Retorna la cantidad de registros existentes en el dataset

        Returns:
            int: Longitud del dataframe
        """
        return self.shape[0]

    def merge_dataset(self, dataset_to_merge, left_on, right_on, how):
        """Combina, bajo ciertos criterios, la información proveniente de un dataset con el del dataset actual

        Args:
            dataset_to_merge (pandas.core.frame.DataFrame): Dataset con el que se va a combinar
            left_on (label or list): Nombre de la(s) columna(s) del dataset actual usada(s) como criterio de combinación
            right_on (label or list): Nombre de la(s) columna(s) del dataset pasado como parámetro usada(s) como criterio de combinación
            how (str): Tipo de combinación a realizarse
        """
        self = self.merge(dataset_to_merge, how=how, left_on=left_on, right_on=right_on)

    @classmethod
    def from_csv(cls, filename, names, encoding="utf-8-sig", separator=","):
        """Genera todos los atributos para una instancia de la clase Dataset a partir de un archivo csv

        Args:
            filename (str): Nombre del archivo csv
            names (list, optional): Lista de columnas
            encoding (str, optional): Codificación usada para leer el archivo csv. Defaults to "utf-8-sig".
            separator(str, optional): Separador de columnas. Defaults to ","
        """
        return cls(read_csv(filename, names=names, encoding=encoding, sep=separator))


class WebDriver(Chrome):
    """_summary_

    Args:
        Chrome (_type_): _description_
    """

    def __init__(self, chrome_options=None, seleniumwire_options=None):
        super().__init__(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options,
            seleniumwire_options=seleniumwire_options,
        )
        self._wait = WebDriverWait(self, 7)
        self.maximize_window()

    def enter_website(self, url):
        """Entra a una página web dado una url

        Args:
            url (str): Link de una página web
        """
        LOGGER.info(f"Accediendo a {url}")
        self.get(url)

    def get_element(self, method, message=""):
        """Función que busca uno o varios elementos ubicados en la página web y los retorna si la búsqueda tenga éxito

        Args:
            method (function): Función usada para la búsqueda de uno o varios elementos ubicados en la página web
            message (str, optional): Mensaje a mostrar en caso la búsqueda falle. Defaults to "".

        Returns:
            Any: El resultado devuelto por la función usada como búsqueda
        """
        return self._wait.until(method, message)


class ScraperFalabellaCategory:
    """Representa a un bot para hacer web scraping en saga falabella

    Attributes:
        time (Tiempo): Objeto de la clase Tiempo que maneja información del tiempo de ejecución del scraper
        df_category (Data): Objeto de la clase Data que maneja información de las categorías extraídas por el scraper
        df_dict_category (Dataset): Objeto de la clase Dataset que funciona como diccionario para mapear las categorías de saga falabella
        df_dict_category_filename (str): Nombre del archivo que contiene el diccionario de datos para mapear las categorías de saga falabella
        driver (WebDriver): Objeto de la clase WebDriver que maneja un navegador para hacer web scraping
    """

    def __init__(self, dict_filename):
        """Genera todos los atributos para una instancia de la clase ScraperFb

        Args:
            dict_filename (str): Nombre del archivo que va a ser usado como diccionario de datos
        """
        LOGGER.info("Inicializando scraper")
        self._time = Tiempo()
        self._df_category = Data()
        # Comprobando si el diccionario para las categorías ya ha sido creado
        if path.isfile(dict_filename):
            self._df_dict_category = Data.from_csv(
                dict_filename, names=DATA_DICT_HEADERS
            )
            LOGGER.info(
                "El archivo de diccionario de categorías se ha definido satisfactoriamente",
            )
        else:
            self._df_dict_category = None
            LOGGER.info(
                "El archivo de diccionario de categorías no se va a utilizar por ser la primera ejecución",
            )
        # Guardar el nombre del archivo en un atributo de clase
        self._df_dict_category_filename = dict_filename
        # Estableciendo las opciones de Chrome
        chrome_options = ChromeOptions()
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.popups": 2,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.add_experimental_option(
            "excludeSwitches", ["enable-logging"]
        )  # Suprimir los mensajes de consola
        # Estableciendo las opciones de seleniumwire
        seleniumwire_options = {"disable_capture": True}  # No guardar ningún request
        self._driver = WebDriver(chrome_options, seleniumwire_options)

    def close_popups(self):
        """Cierra todas las ventanas emergentes"""
        self._driver.get_element(
            EC.element_to_be_clickable((By.CLASS_NAME, "dy-lb-close"))
        ).click()
        self._driver.get_element(
            EC.element_to_be_clickable((By.ID, "testId-accept-cookies-btn"))
        ).click()

    def extract_text(self, pattern, text, n=1):
        """Extrae el texto deseado de una cadena dado una expresión regular

        Args:
            pattern (str): Expresión regular a utilizar para la búsqueda
            text (str): Texto donde se va a realizar la búsqueda
            n (int, optional): Número de grupo a recuperar. Defaults to 1.

        Returns:
            str or None: Texto encontrado o vacío
        """
        groups = search(pattern, text)
        return groups.group(n) if groups else groups

    def get_menu_links(self):
        """Función que navega por el menú de Saga Falabella y extrae todos los links

        Returns:
            list: Lista de enlaces
        """

        menu_links = []
        LOGGER.info("Accediendo al menú principal de saga falabella")
        self._driver.get_element(
            EC.element_to_be_clickable(
                (By.CLASS_NAME, "MarketplaceHamburgerBtn-module_hamburgerBtn__61t-r")
            )
        ).click()

        LOGGER.info(
            "Registrando la lista de categorías que nos muestra el menú principal"
        )
        category_list = self._driver.get_element(
            EC.visibility_of_all_elements_located(
                (
                    By.XPATH,
                    "//div[@class='FirstLevelCategories-module_categories__x82VK']",
                )
            )
        )

        LOGGER.info("Filtrando categorías que son creadas temporalmente")
        category_list = list(
            filter(
                lambda x: x,
                list(
                    THREAD.map(
                        lambda x: x if self.is_permanent_category(x.text) else None,
                        category_list,
                    )
                ),
            )
        )

        LOGGER.info("Navegando por el menú principal")
        for category in category_list:
            try:
                category.click()
                subcategory_list = self._driver.get_element(
                    EC.presence_of_all_elements_located(
                        (
                            By.XPATH,
                            "//li[@class='SecondLevelCategories-module_thirdLevelCategory__2ZQFF']/a",
                        )
                    )
                )
                menu_links += list(
                    THREAD.map(
                        lambda x: sub(r"\?.+", "", x.get_attribute("href")),
                        subcategory_list,
                    )
                )

            except TimeoutException:
                LOGGER.error(
                    "Tiempo agotado para recuperar las subcategorías mostradas por el menú principal de saga falabella",
                )

        LOGGER.info("Filtrando links duplicados")
        menu_links = list(set(menu_links))

        LOGGER.info("Filtrando los links que no pertenecen a una categoría")
        menu_links = list(
            filter(
                lambda x: x,
                list(
                    THREAD.map(
                        lambda x: x if self.is_url_category(x) else None,
                        menu_links,
                    )
                ),
            )
        )
        LOGGER.info(f"Se han extraído satisfactoriamente {len(menu_links)} links")
        return menu_links

    def is_permanent_category(self, text):
        """Comprueba si la categoría mostrada por el menú es creada solo por temporadas o es permanente

        Args:
            text (str): Nombre de la categoría

        Returns:
            bool: Booleano
        """
        return text.split("\n")[-1] not in ["NUEVO", "Emprendedores", "SALE"]

    def is_url_category(self, url):
        """Comprueba si el link no pertenece a una categoría de falabella

        Args:
            url (str): Enlace web

        Returns:
            bool: Booleano que indica si el link pertenece o no a una categoría de falabella
        """
        return url.find("category") != -1

    def get_category_info(self, subcategory_links):
        """Retorna un conjunto de datos que contiene toda la información de las categorías de saga falabella

        Returns:
            Data: Instancia de la clase Data
        """
        # Diccionario de datos que almacena la información de las categorías de saga falabella
        category_info_link = {}
        # Diccionario de datos que almacena las categorías de los links recorridos
        category_dict_info = {
            "Link_subcat": [],
            "Name": [],
            "Link_cat": [],
        }

        LOGGER.info(
            "Recopilando los links de las categorías principales a partir de los links de las subcategorías",
        )
        # Comprobando si el diccionario de links recorridos ha sido definido
        if self._df_dict_category:
            LOGGER.info(
                "Usando el diccionario de datos para encontrar las categorías principales",
            )
            temp_subcat_links = []
            # Recorriendo los links de cada subcategoría
            for link in subcategory_links:
                results = self._df_dict_category.find_rows(DATA_DICT_HEADERS[0], link)
                # Comprobando que existan resultados
                if len(results) > 0:
                    # Guardando la información de la primera coincidencia
                    _, name, url_cat = results[0]
                    category_info_link[name] = url_cat
                else:
                    # Guardar los links que aún faltan recorrer
                    temp_subcat_links.append(link)

            subcategory_links = temp_subcat_links
            del temp_subcat_links

        LOGGER.info("Cerrando ventana emergente molesta")
        try:
            self._driver.enter_website(subcategory_links[0])
            self._driver.get_element(
                EC.element_to_be_clickable((By.ID, "testId-modal-close"))
            ).click()
        except:
            pass

        LOGGER.info(f"Se va a recorrer solo {len(subcategory_links)} links")
        for link in subcategory_links:
            self._driver.enter_website(link)
            no_error = True

            # Comprobando que el link no te rediriga a otra página
            current_link = self._driver.execute_script("return document.URL")
            if not self.is_url_category(current_link):
                LOGGER.info(
                    f"No se va a extraer categorías del link {link}, pues te redirige a otro link: {current_link}",
                )
                continue

            # Navegar hasta la categoría padre de la subcategoría
            while no_error:
                try:
                    self._driver.get_element(
                        EC.presence_of_element_located(
                            (By.XPATH, "//a[@class='jsx-2883309125 l1category']")
                        )
                    ).click()

                except ElementNotInteractableException:
                    LOGGER.info("Se ha conseguido llegar hasta la categoría principal")
                    no_error = False

            url_cat = self._driver.execute_script("return document.URL")
            name_cat = self._driver.get_element(
                EC.presence_of_element_located(
                    (By.XPATH, "//h1[@class='jsx-2883309125 l2category']")
                ),
            ).text

            LOGGER.info(f"Categoría Obtenida: {name_cat}")
            # Guardando las nuevas incidencias al diccionario de categorías
            category_dict_info["Link_subcat"].append(link)
            category_dict_info["Name"].append(name_cat)
            category_dict_info["Link_cat"].append(url_cat)
            category_info_link[name_cat] = url_cat

        df_dict_info = Data(category_dict_info)
        # Comprobando si existen nuevas incidencias
        if df_dict_info.length() == 0:
            LOGGER.info(
                "No se va a guardar el diccionario de links recorridos. Razón: No han aparecido nuevas incidencias",
            )
        else:
            if self._df_dict_category:
                # Agregar las nuevas incidencias a las ya existentes
                self._df_dict_category.concat_dataset(df_dict_info, axis=0)
            else:
                self._df_dict_category = df_dict_info
            self._df_dict_category.sort_values(DATA_DICT_HEADERS[0])
            self._df_dict_category.to_csv(
                self._df_dict_category_filename,
                header=False,
                index=False,
                encoding="utf-8-sig",
            )
            LOGGER.info(
                f"Diccionarios de datos guardados satisfactoriamente con el nombre de {self._df_dict_category_filename}",
            )

        # Filtrando la categoría Especiales
        category_info_link = {
            key: category_info_link[key]
            for key in category_info_link
            if key != "Especiales"
        }
        cat_info_values = category_info_link.values()
        LOGGER.info("Categorías principales recuperadas satisfactoriamente\n")
        return Data(
            {
                "Id_0": [self.extract_text(r"/.*/(.*)/", x) for x in cat_info_values],
                "Name_0": category_info_link.keys(),
                "Link_0": cat_info_values,
            }
        )

    def get_subcategory_info(self, column_values, whole_links):
        """Retorna un conjunto de datos que contiene toda la información de las subcategorías de saga falabella

        Args:
            column_values (list): Lista de valores a ser usados para la extracción de subcategorías

        Returns:
            Dataset: Instancia de la clase Dataset
        """
        subcategory_info = {
            "Id": [],
            "Id_subcat": [],
            "Subcategory": [],
            "Link_subcat": [],
        }
        for category_level in column_values:
            try:
                API_PARAMS["categoryId"] = category_level[0]
                API_PARAMS["categoryName"] = quote_plus(category_level[1])
                response = get(API_URL, headers=API_HEADERS, params=API_PARAMS)
                filters_value = response.json()["data"]["facets"][:4]
                for filter_value in filters_value[::-1]:
                    if filter_value["name"] == "Categoría":
                        data_values = filter_value["values"]
                        for item in data_values:
                            title = item["title"]
                            id_cat = item["id"]
                            subcategory_info["Link_subcat"].append(
                                "https://www.falabella.com.pe/falabella-pe/category/"
                                + id_cat
                                + "/"
                                + title.replace(" ", "-")
                            )
                            subcategory_info["Id"].append(category_level[0])
                            subcategory_info["Subcategory"].append(title)
                            subcategory_info["Id_subcat"].append(id_cat)
                        break

            except (IndexError, JSONDecodeError, KeyError):
                pass

        index_values = [
            id_index
            for id_index, id_subcat in enumerate(subcategory_info["Id_subcat"])
            if id_subcat in whole_links
        ]
        df_subcat_info = Data(subcategory_info)
        if len(index_values) > 0:
            df_subcat_info.drop(index_values, inplace=True)

        return df_subcat_info

    def extract_categories(self, level):
        """Extrae la información de las categorías de saga falabella hasta cierto nivel de profundidad

        Args:
            level (int): Profundidad del árbol de categorías de saga falabella
        """
        LOGGER.info(
            f"Extrayendo el árbol de categorías de saga falabella con profundidad {level}",
        )
        if level <= 0:
            LOGGER.error(
                f"La cantidad de niveles de jerarquía de la clasificación de las categorías debe ser mayor o igual a 0",
            )
            self._driver.quit()
            return

        LOGGER.info("Entrando a la página web de la tienda de saga falabella")
        self._driver.enter_website(URL_FALABELLA)
        WHOLE_LINKS = []
        menu_links = self.get_menu_links()
        self._df_category = self.get_category_info(menu_links)
        df_subcategory = self._df_category
        WHOLE_LINKS += self._df_category.get_column_values("Id_0")
        self._driver.quit()
        if level == 1:
            LOGGER.info(
                f"Se ha especificado nivel de profundidad {level}. No se va a extraer la información de las subcategorías.",
            )
            return

        LOGGER.info("Extrayendo información de las subcategorías")
        for i in range(1, level):
            LOGGER.info(f"Obteniendo información de las subcategorías de nivel {i}")
            # Definiendo la columna a ser usada como nexo para el merge
            id_prev = "Id_" + str(i - 1)
            name_prev = "Name_" + str(i - 1)
            df_subcategory = self.get_subcategory_info(
                df_subcategory.get_column_values([id_prev, name_prev]), WHOLE_LINKS
            )

            if df_subcategory.length() == 0:
                level = i
                LOGGER.info(
                    f"Se ha llegado al máximo de profundidad con un valor de {level}.",
                )
                break

            # Renombrando las columnas del dataset
            df_subcategory.rename(
                {
                    "Id": id_prev,
                    "Subcategory": "Name_" + str(i),
                    "Link_subcat": "Link_" + str(i),
                    "Id_subcat": "Id_" + str(i),
                },
                axis=1,
                inplace=True,
            )
            df_subcategory.drop_duplicates(
                ["Id_" + str(i)], keep="first", inplace=True, ignore_index=True
            )
            # Combinando el dataset que contiene la información de las categorías y subcategorías
            WHOLE_LINKS += df_subcategory.get_column_values("Id_" + str(i))
            self._df_category.merge_dataset(df_subcategory, id_prev, id_prev, "left")
            LOGGER.info(f"Subcategorías de nivel {i} recuperadas satisfactoriamente\n")
        LOGGER.info(
            f"Extracción de las categorías con un nivel de profundidad {level} completado satisfactoriamente\n",
        )

    def save_data(self, folder, filename):
        """Guarda los datos o errores obtenidos durante la ejecución del scraper

        Args:
            folder (str): Ruta del archivo
            filename (str): Nombre del archivo
            encoding (str): Codificación usada para guardar el archivo
        """
        # Registrando toda la información de las categorías extraídas por el scraper
        dataset = self._df_category
        # Registrando la cantidad de información que contiene el dataset
        quantity = dataset.length()
        # Registrando la cantidad de categorías extraídas por el scraper
        self._time.quantity = quantity

        # Comprobando que el dataset contenga información
        if quantity == 0:
            LOGGER.info(
                f"El archivo de datos no se va a guardar por no tener información",
            )
            return

        # Generando la ruta donde se va a guardar la información
        datetime_obj = datetime.strptime(self._time.execution_date, "%d/%m/%Y")
        filepath = path.join(folder, datetime_obj.strftime("%d-%m-%Y"))
        filename = (
            filename
            + "_"
            + datetime_obj.strftime("%d%m%Y")
            + "_"
            + str(quantity)
            + ".csv"
        )

        # Verificando si la ruta donde se va a guardar la información existe
        if not path.exists(filepath):
            # Creando la ruta donde se va a guardar la información
            makedirs(filepath)
        dataset.to_csv(
            path.join(filepath, filename),
            header=False,
            index=False,
            encoding="utf-8-sig",
        )
        LOGGER.info(
            f"Archivo {filename} ha sido guardado correctamente en la ruta {filepath}",
        )

    def save_time_execution(self, filename, sheet_name):
        """Guarda la información del tiempo de ejecución del scraper

        Args:
            filename (str): Nombre del archivo
            sheet_name (str): Nombre de la hoja de cálculo
        """
        # Guardando los parametros finales del tiempo de ejecución del scraper
        self._time.set_param_final()
        LOGGER.info("Guardando tiempos")
        # Variable que indica si el encabezados existe o no en el archivo de excel
        header_exist = False

        # Verificando si el archivo existe o no
        if path.isfile(filename):
            wb_time = load_workbook(filename)
            # Comprobando si ya existe un sheet con el nombre indicado en la variable sheet_name
            if sheet_name not in [ws.title for ws in wb_time.worksheets]:
                # Creando un nuevo sheet
                wb_time.create_sheet(sheet_name)
            else:
                header_exist = True
        else:
            wb_time = Workbook()
            wb_time.worksheets[0].title = sheet_name

        # Seleccionar el sheet deseado donde se va a guardar la información
        worksheet = wb_time[sheet_name]

        # Comprobando si el encabezados existen o no
        if not header_exist:
            keys = [
                "Fecha",
                "Hora Inicio",
                "Hora Fin",
                "Cantidad",
                "Tiempo Ejecucion (min)",
                "Categorias / Minuto",
                "Errores",
            ]
            worksheet.append(keys)

        values = list(self._time.__dict__.values())[1:]
        worksheet.append(values)
        wb_time.save(filename)
        wb_time.close()
        LOGGER.info("Tiempos Guardados Correctamente")


def config_log(log_folder, log_filename, log_file_mode="w", log_file_encoding="utf-8"):
    """Función que configura los logs para rastrear al programa

    Args:
        log_folder (str): Carpeta donde se va a generar el archivo log
        log_filename (str): Nombre del archivo log a ser generado
        log_file_mode (str, optional): Modo de guardado del archivo. Defaults to "w".
        log_file_encoding (str, optional): Codificación usada para el archivo. Defaults to "utf-8".
    """
    # Generando la ruta donde se va a guardar los registros de ejecución
    log_path = path.join(log_folder, CURRENT_DATE.strftime("%d-%m-%Y"))
    log_filename = log_filename + "_" + CURRENT_DATE.strftime("%d%m%Y") + ".log"

    # Verificando si la ruta donde se va a guardar los registros de ejecución existe
    if not path.exists(log_path):
        makedirs(log_path)

    formatter = Formatter("%(asctime)s - %(levelname)s - %(message)s")
    stream_handler = StreamHandler(stdout)
    stream_handler.setFormatter(formatter)
    file_handler = FileHandler(
        path.join(log_path, log_filename), log_file_mode, log_file_encoding
    )
    file_handler.setFormatter(formatter)
    LOGGER.handlers = [stream_handler, file_handler]
    LOGGER.propagate = False
    LOGGER.setLevel(INFO)


def validate_params(parameters):
    """Función que valida si los parámetros a usar están definidos

    Args:
        parameters (list): Lista de parámetros

    Returns:
        bool: Booleano que indica si los parámetros están definidos o no
    """
    for param in parameters:
        if not param or param == "":
            return False
    return True


def main():
    try:
        # Formato para el debugger
        config_log("Log", "fb_ropa_log")

        LOGGER.info("Validando parámetros a usar")
        if not validate_params(
            [
                DATA_FILENAME,
                DATA_FOLDER,
                DATA_DICT_FILENAME,
                TIME_FILENAME,
                TIME_SHEET_NAME,
                URL_FALABELLA,
            ]
        ):
            LOGGER.error("Parámetros incorrectos")
            return
        LOGGER.info("Parámetros válidos")

        scraper = ScraperFalabellaCategory(DATA_DICT_FILENAME)

        LOGGER.info("Cerrando ventanas emergentes")
        scraper.close_popups()

        LOGGER.info("Extrayendo las categorias de falabella")
        scraper.extract_categories(5)

        LOGGER.info("Guardando toda la información generada por el scraper")
        scraper.save_data(DATA_FOLDER, DATA_FILENAME)
        scraper.save_time_execution(TIME_FILENAME, TIME_SHEET_NAME)
        LOGGER.info("Programa finalizado")

    except Exception as error:
        Error(error).imprimir_error()
        LOGGER.error("Programa ejecutado con fallos")
    finally:
        # Liberar el archivo log
        shutdown()


if __name__ == "__main__":
    main()
