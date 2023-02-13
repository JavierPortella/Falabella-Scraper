from json import loads
from datetime import datetime, timedelta
from logging import (
    basicConfig,
    ERROR,
    FileHandler,
    INFO,
    log,
    shutdown,
    StreamHandler,
)
from os import environ, makedirs, path
from re import sub
from time import localtime, strftime, time
from traceback import TracebackException

from openpyxl import load_workbook, Workbook
from pandas import DataFrame, read_csv
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.remote_connection import LOGGER as seleniumLogger
from selenium.webdriver.support.wait import WebDriverWait
from urllib3.connectionpool import log as urllibLogger
from webdriver_manager.chrome import ChromeDriverManager


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

    def __init__(self, current_date):
        """Genera todos los atributos para una instancia de la clase Tiempo

        Args:
            current_date (datetime.date): Fecha en la que se ejecuta el scraper
        """
        self._start_time = time()
        self._execution_date = current_date.strftime("%d/%m/%Y")
        self._start_hour = strftime("%H:%M:%S", localtime(self._start_time))
        self._end_hour = None
        self._quantity = 0
        self._time_execution = None
        self._category_per_min = None
        self._num_errors = 0
        log(INFO, f"Hora de inicio: {self._start_hour}")

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
        """Registra los parámetros finales para medir el tiempo de ejecución del scraper"""
        end = time()
        self._end_hour = strftime("%H:%M:%S", localtime(end))
        total = end - self._start_time
        self._time_execution = str(timedelta(seconds=total)).split(".")[0]
        self._category_per_min = round(self._quantity / (total / 60), 2)
        log(INFO, f"Se halló {self._num_errors} errores")
        log(INFO, f"Categorías Extraídas: {self._quantity}")
        log(INFO, f"Hora Fin: {self._end_hour}")


class Errores:
    """Representa a los errores ocurridos durante la ejecución de un scraper

    Attributes:
        errors (dict): Conjunto de datos que contiene toda información de los errores ocurridos durante la ejecución del scraper
    """

    def __init__(self):
        """
        Genera todos los atributos para una instancia de la clase Errores
        """
        self._errors = {
            "Clase": [],
            "Mensaje": [],
            "Linea de Error": [],
            "Codigo Error": [],
            "Origen": [],
            "Publicacion": [],
        }

    @property
    def errors(self):
        """Retorna el valor actual del atributo errors"""
        return self._errors

    def add_new_error(self, error, description, link):
        """Agrega la información de un nuevo error al conjunto de datos errors

        Args:
            error (Exception): Error ocurrido durante la ejecución del scraper
            description (str): Breve descripción del error
            link (str): Enlace de una categoría de la página de saga falabella
        """
        traceback_error = TracebackException.from_exception(error)
        error_stack = traceback_error.stack[0]
        self._errors["Clase"].append(traceback_error.exc_type)
        self._errors["Mensaje"].append(traceback_error._str)
        self._errors["Linea de Error"].append(error_stack.lineno)
        self._errors["Codigo Error"].append(error_stack.line)
        self._errors["Origen"].append(description)
        self._errors["Publicacion"].append(link)


class Dataset:
    """Representa al conjunto de datos generado por el scraper

    Attributes:
        dataset (pandas.core.frame.DataFrame): Dataframe que contiene toda información de las categorías de la página de saga falabella
    """

    def __init__(self, data):
        """Genera todos los atributos para una instancia de la clase Dataset

        Args:
            data (pandas.core.frame.DataFrame): Contiene la información de las categorías
        """
        if isinstance(data, DataFrame):
            self._dataset = data
        else:
            self._dataset = DataFrame(data)

    @property
    def dataset(self):
        """Retorna el valor actual del diccionario de datos dataset"""
        return self._dataset

    @classmethod
    def from_csv(cls, filename, names, encoding="utf-8-sig"):
        """Genera todos los atributos para una instancia de la clase Dataset a partir de un archivo csv

        Args:
            filename (str): Nombre del archivo csv
            names (list, optional): Lista de columnas
            encoding (str, optional): Codificación usada para leer el archivo csv. Defaults to "utf-8-sig".
        """
        return cls(read_csv(filename, names=names, encoding=encoding))

    def filter_duplicate_values(self, column_filters):
        """Elimina todos los registros con valores duplicados excepto la primera aparición del mismo

        Args:
            column_filters (list): Columna o columnas para identificar valores duplicados
        """
        self._dataset.drop_duplicates(
            column_filters, keep="first", inplace=True, ignore_index=True
        )

    def find_rows(self, column_name, value):
        """Buscar todas las filas que coincidan con el criterio de búsqueda

        Args:
            column_name (str): Columna donde se va a realizar la búsqueda
            value (str): Valor a buscar

        Returns:
            list: Lista de registros que coinciden con el criterio de búsqueda
        """
        return self._dataset[self._dataset[column_name] == value].values.tolist()

    def get_column_names(self):
        """Retorna una lista con los nombres de las columnas existentes en el dataset

        Returns:
            list: Lista de nombres de las columnas
        """
        return self._dataset.columns.tolist()

    def get_column_values(self, column_name):
        """Retorna una lista de valores de una columna existente en el dataset

        Args:
            column_name (str): Nombre de la columna

        Returns
            list: Lista de valores
        """
        return self._dataset[column_name].values.tolist()

    def length(self):
        """Retorna la cantidad de registros existentes en el dataset

        Returns:
            int: Longitud del dataframe
        """
        return len(self._dataset)

    def merge_dataset(self, dataset_to_merge, left_on, right_on, how):
        """Combina, bajo ciertos criterios, la información proveniente de un dataset con el del dataset actual

        Args:
            dataset_to_merge (pandas.core.frame.DataFrame): Dataset con el que se va a combinar
            left_on (label or list): Nombre de la(s) columna(s) del dataset actual usada(s) como criterio de combinación
            right_on (label or list): Nombre de la(s) columna(s) del dataset pasado como parámetro usada(s) como criterio de combinación
            how (str): Tipo de combinación a realizarse
        """
        self._dataset = self._dataset.merge(
            dataset_to_merge, how=how, left_on=left_on, right_on=right_on
        )

    def rename_columns(self, dict_columns):
        """Renombra una o varias columnas del dataset

        Args:
            dict_columns (dict): Diccionario que contiene tanto los nombres actuales de las columnas como los nuevos nombres de las columnas
        """
        self._dataset.rename(dict_columns, axis=1, inplace=True)

    def save_dataset(self, filename, header=True, mode="w", encoding="utf-8-sig"):
        """Guarda toda la información del dataset en un archivo .csv

        Args:
            filename (str): Nombre del archivo
            header (bool, optional): Indica si se va a guardar o no los encabezados. Defaults to True.
            mode (str, optional): Modo de guardado del archivo. Defaults to "w".
            encoding (str, optional): Codificación usada para guardar el archivo. Defaults to "utf-8-sig".
        """
        self._dataset.to_csv(
            filename, header=header, index=False, mode=mode, encoding=encoding
        )


class ScraperFalabellaCategory:
    """Representa a un bot para hacer web scraping en saga falabella

    Attributes:
        time (Tiempo): Objeto de la clase Tiempo que maneja información del tiempo de ejecución del scraper
        errors (Errores): Objeto de la clase Errores que maneja información de los errores ocurridos durante la ejecución del scraper
        df_category (Dataset): Objeto de la clase Dataset que maneja información de las categorías extraídas por el scraper
        df_dict_category (Dataset): Objeto de la clase Dataset que funciona como diccionario para mapear las categorías de saga falabella
        df_dict_category_filename (str): Nombre del archivo que contiene el diccionario de datos para mapear las categorías de saga falabella
        driver (webdriver.Chrome): Objeto de la clase webdriver que maneja un navegador para hacer web scraping
        wait (WebDriverWait): Objeto de la clase WebDriverWait que maneja el Tiempo de espera durante la ejecución del scraper
    """

    def __init__(self, current_date, dict_filename):
        """Genera todos los atributos para una instancia de la clase ScraperFb

        Args:
            current_date (datetime.date): Fecha en la que se ejecuta el scraper
            dict_filename (str): Nombre del archivo que va a ser usado como diccionario de datos
        """
        log(INFO, "Inicializando scraper")
        self._time = Tiempo(current_date)
        self._errors = Errores()
        self._df_category = None
        if path.isfile(dict_filename):
            self._df_dict_category = Dataset.from_csv(
                dict_filename, names=["Link_subcat", "Name", "Link_cat"]
            )
            log(
                INFO,
                "El archivo de diccionario de categorías se ha definido satisfactoriamente",
            )
        else:
            self._df_dict_category = None
            log(INFO, "El archivo de diccionario de categorías no se ha definido")

        self._df_dict_category_filename = dict_filename
        options = ChromeOptions()
        prefs = {"profile.default_content_setting_values.notifications": 2}
        options.add_experimental_option("prefs", prefs)
        self._driver = Chrome(ChromeDriverManager().install(), options=options)
        self._wait = WebDriverWait(self._driver, 8)

    def enter_website(self, url):
        """Entra a una página web dado una url

        Args:
            url (str): Link de una página web
        """
        log(INFO, f"Accediendo a {url}")
        self._driver.get(url)

    def maximize_window(self):
        """Pone a pantalla completa el navegador"""
        self._driver.maximize_window()

    def get_element(self, selector, path):
        """Localiza y retorna un elemento en la página web dado un criterio de búsqueda

        Args:
            selector (str): Selector a ser usado para localizar un elemento en la página web
            path (str): Ruta de un elemento web a ser usado por el selector

        Returns:
            selenium.webdriver.remote.webelement.WebElement: Elemento de la página web encontrado
        """
        return self._wait.until(lambda x: x.find_element(selector, path))

    def get_elements(self, selector, path):
        """Localiza y retorna una lista de todos los elementos en la página web que coincidan con un criterio de búsqueda

        Args:
            selector (str): Selector a ser usado para localizar varios elementos en la página web
            path (str): Ruta de los elementos web a ser usado por el selector

        Returns:
            list: Lista de elementos de la página web
        """
        return self._wait.until(lambda x: x.find_elements(selector, path))

    def close_popups(self):
        """Cierra todas las ventanas emergentes"""
        log(INFO, "Cerrando ventanas emergentes")
        self._driver.delete_all_cookies()
        self.get_element(By.ID, "testId-accept-cookies-btn").click()
        # self.get_element(By.CLASS_NAME, "dy-lb-close").click()

    def is_url_category(self, url):
        """Comprueba si el link pertenece a una categoría de saga falabella

        Args:
            url (_type_): Enlace web

        Returns:
            bool: Booleano que indica si el link pertenece o no a una categoría de saga falabella
        """
        return url.find("category") != -1

    def get_category_info(self):
        """Retorna un conjunto de datos que contiene toda la información de las categorías de saga falabella

        Returns:
            Dataset: Instancia de la clase Dataset
        """
        log(INFO, "Obteniendo información de las categorías principales")
        # Accediendo al menú principal de saga falabella
        self.get_element(By.CLASS_NAME, "TopMenu-module_categoryWrapper__Q_tEE").click()

        # Registrando la lista de subcategorías que nos muestra el menú princial de saga falabella
        category_list = self.get_elements(
            By.XPATH, "//a[@class='SideMenu-module_itemWrapper__3IXOl']"
        )
        # Lista que contiene los links de las subcategorías de saga falabella
        subcategory_links = []

        # Diccionario de datos que almacena la información de las categorías de saga falabella
        category_info = {}

        # Diccionario de datos que almacena las categorías de los links recorridos
        category_dict_info = {"Link_subcat": [], "Name": [], "Link_cat": []}

        log(INFO, f"Navegando por el menú principal de saga falabella")
        for category in category_list:
            try:
                # Dando click a una categoría mostrada por el menú principal
                category.click()

                # Extrayendo los links de las subcategorías de la categoría actualmente seleccionada
                subcategory_list = self.get_elements(
                    By.XPATH,
                    "//a[@class='SubCategories-module_hover-effect__1E3TD SubCategories-module_list-item__6XLMU']",
                )

                # Recorriendo la lista de subcategorías de la categoría actualmente seleccionada
                for subcategory in subcategory_list:
                    # Recuperando el link de la subcategoría sin parámetros adicionales
                    url_subcat = sub(r"\?.+", "", subcategory.get_attribute("href"))

                    # Comprobando que el link de la subcategoría contenga category
                    if self.is_url_category(url_subcat):
                        # Guardando el link de la subcategoría en una lista
                        subcategory_links.append(url_subcat)
                    else:
                        log(
                            INFO,
                            f"El link {url_subcat} no corresponde a una categoría de saga falabella",
                        )

            except TimeoutException as error:
                log(
                    ERROR,
                    "Tiempo agotado para recuperar las subcategorías mostradas por el menú principal de saga falabella",
                )
                self._errors.add_new_error(error, "Menú de categorías", None)

        # Filtrando links duplicados
        subcategory_links = list(set(subcategory_links))
        subcategory_links.sort()

        log(INFO, "Cerrando ventana emergente molesta")
        self.enter_website(
            "https://tienda.falabella.com.pe/falabella-pe/category/cat4100481/Moda-Hombre"
        )
        self.get_element(By.ID, "testId-modal-close").click()

        log(
            INFO,
            "Recopilando los links de las categorías principales a partir de los links de las subcategorías",
        )
        # Comprobando si el diccionario de links recorridos ha sido definido
        if self._df_dict_category:
            temp_subcat_links = []
            # Recorriendo los links de cada subcategoría
            for link in subcategory_links:
                # Buscando si el link a recorrer ya existe en el diccionario de links
                results = self._df_dict_category.find_rows(
                    self._df_dict_category.get_column_names()[0], link
                )
                # Comprobando que existan resultados
                if len(results) > 0:
                    # Extrayendo la primera coincidencia
                    _, name, url_cat = results[0]
                    # Guardando el nombre y link de la categoría principal
                    category_info[name] = url_cat
                    log(
                        INFO,
                        "Se ha conseguido encontrado en el diccionario la categoría principal",
                    )
                    log(INFO, f"Categoría Obtenida: {name}")
                else:
                    # Guardar los links que aún faltan recorrer
                    temp_subcat_links.append(link)
            subcategory_links = temp_subcat_links

        log(INFO, f"Se va a recorrer solo {len(subcategory_links)} links")
        # Recorriendo la lista con los links que aún faltan por recorrer
        for link in subcategory_links:
            # Entrando al link de una subcategoría
            self.enter_website(link)
            # Flag que indica si se ha llegado a la categoría principal
            no_error = True

            # Comprobando que el link no te rediriga a otra página
            current_link = self._driver.execute_script("return document.URL")
            if not self.is_url_category(current_link):
                log(INFO, f"No se va a extraer categorías del link {link}")
                log(
                    INFO,
                    f"Razón: El link {link} te redirige a otro link: {current_link}",
                )
                continue

            # Mientras no sea la categoría principal
            while no_error:
                try:
                    # Navegar a la categoría padre de la subcategoría
                    self.get_element(
                        By.XPATH, "//a[@class='jsx-2883309125 l1category']"
                    ).click()

                except ElementNotInteractableException as error:
                    log(INFO, "Se ha conseguido llegar hasta la categoría principal")
                    self._errors.add_new_error(
                        error, "Extracción categoría principal", link
                    )
                    no_error = False

            url_cat = self._driver.execute_script("return document.URL")

            # Obteniendo el nombre de la categoría principal
            name = self.get_element(
                By.XPATH, "//h1[@class='jsx-2883309125 l2category']"
            ).text

            # Guardando las nuevas incidencias
            category_dict_info["Link_subcat"].append(link)
            category_dict_info["Name"].append(name)
            category_dict_info["Link_cat"].append(url_cat)

            # Comprobando que la categoría no tenga como nombre Especiales
            if name == "Especiales":
                log(
                    INFO,
                    f"La categoría {name} no se va a guardar por ser una categoría que engloba a otras categorías",
                )
                continue

            log(INFO, f"Categoría Obtenida: {name}")
            # Guardando el nombre y link de la categoría principal
            category_info[name] = url_cat

        df_dict_info = Dataset(category_dict_info)
        if df_dict_info.length() == 0:
            log(
                INFO,
                "No se va a guardar el diccionario de links recorridos. Razón: No han aparecido nuevas incidencias",
            )
        else:
            df_dict_info.save_dataset(
                self._df_dict_category_filename, header=False, mode="a"
            )
            log(
                INFO,
                f"Diccionarios de datos guardados satisfactoriamente con el nombre de {self._df_dict_category_filename}",
            )

        log(INFO, "Categorías principales recuperadas satisfactoriamente\n")
        return Dataset({"Name": category_info.keys(), "Link_0": category_info.values()})

    def get_subcategory_info(self, category_links):
        """Retorna un conjunto de datos que contiene toda la información de las subcategorías de saga falabella

        Args:
            category_links (list): Lista de links de las categorías de saga falabella

        Returns:
            Dataset: Instancia de la clase Dataset
        """
        subcategory_info = {
            "Link": [],
            "Subcategory": [],
            "Link_1": [],
        }
        for category_level in category_links:
            try:
                self.enter_website(category_level)
                data = self.get_element(By.XPATH, "//script[@id='__NEXT_DATA__']")
                data_json = loads(data.get_attribute("text"))
                filters_value = data_json["props"]["pageProps"]["facets"][:3]
                for filter_value in filters_value:
                    if filter_value["name"] == "Categoría":
                        data_values = filter_value["values"]
                        for item in data_values:
                            title = item["title"]
                            subcategory_info["Link_1"].append(
                                "https://tienda.falabella.com.pe/falabella-pe/category/"
                                + item["id"]
                                + "/"
                                + title.replace(" ", "-")
                            )
                            subcategory_info["Link"].append(category_level)
                            subcategory_info["Subcategory"].append(title)
                        break

            except (IndexError, KeyError, TimeoutException) as error:
                log(ERROR, f"Error: {error}\nEnlace: {category_level}")
                self._errors.add_new_error(
                    error, "Extracción categorías secundarias", category_level
                )
        return Dataset(subcategory_info)

    def extract_categories(self, level):
        """Extrae la información de las categorías de saga falabella hasta cierto nivel de profundidad

        Args:
            level (int): Profundidad del árbol de categorías de saga falabella
        """
        log(
            INFO,
            f"Extrayendo el árbol de categorías de saga falabella con profundidad {level}",
        )
        if level < 0:
            log(
                ERROR,
                f"La cantidad de niveles de jerarquía de la clasificación de las categorías debe ser mayor o igual a 0",
            )
            return

        self._df_category = self.get_category_info()
        df_subcategory = self._df_category

        if level == 1:
            log(
                INFO,
                f"Se ha especificado nivel de profundidad {level}. No se va a extraer la información de las subcategorías.",
            )
            return

        log(INFO, "Extrayendo información de las subcategorías")
        for i in range(1, level + 1):
            log(INFO, f"Obteniendo información de las subcategorías de nivel {i}")
            # Definiendo la columna a ser usada como nexo para el merge
            join_col = "Link_" + str(i - 1)
            df_subcategory = self.get_subcategory_info(
                df_subcategory.get_column_values(join_col)
            )

            if df_subcategory.length() == 0:
                level = i
                log(
                    INFO, f"Se ha llegado al máximo de profundidad con un valor de {i}."
                )
                break

            # Renombrando las columnas del dataset
            df_subcategory.rename_columns(
                {
                    "Link": join_col,
                    "Subcategory": "Subcategory_" + str(i),
                    "Link_1": "Link_" + str(i),
                }
            )
            # Combinando el dataset que contiene la información de las categorías y subcategorías
            self._df_category.merge_dataset(
                df_subcategory.dataset, join_col, join_col, "left"
            )
            log(INFO, f"Subcategorías de nivel {i} recuperadas satisfactoriamente\n")
        log(
            INFO,
            f"Extracción de las categorías con un nivel de profundidad {level} completado satisfactoriamente\n",
        )

    def save_data(self, filetype, folder, filename):
        """Guarda los datos o errores obtenidos durante la ejecución del scraper

        Args:
            filetype (str): {'Data', 'Error'}. Indica si la información son datos de las categorías o de los errores.
            folder (str): Ruta del archivo
            filename (str): Nombre del archivo
            encoding (str): Codificación usada para guardar el archivo
        """
        log(INFO, f"Guardando {filetype}")
        # Comprobando si el valor ingresado para la variable filetype es correcto
        if filetype == "Data":
            # Registrando toda la información de las categorías extraídas por el scraper
            dataset = self._df_category
            # Registrando la cantidad de categorías extraídas por el scraper
            self._time.quantity = dataset.length()
        elif filetype == "Error":
            # Registrando toda la información de los errores ocurridos durante la ejecución del scraper
            dataset = Dataset(self._errors.errors)
            # Registrando la cantidad de errores ocurridos durante la ejecución del scraper
            self._time.num_errors = dataset.length()
        else:
            log(
                INFO,
                f"El archivo de tipo {filetype} no está admitido. Solo se aceptan los valores Data y Error",
            )
            log(
                ERROR,
                f"El archivo de tipo {filetype} no se va a guardar por no ser de tipo Data o Error",
            )
            return

        # Registrando la cantidad de información que contiene el dataset
        quantity = dataset.length()

        # Comprobando que el dataset contenga información
        if quantity == 0:
            log(
                INFO,
                f"El archivo de tipo {filetype} no se va a guardar por no tener información",
            )
            return

        # Generando la ruta donde se va a guardar la información
        datetime_obj = datetime.strptime(self._time.execution_date, "%d/%m/%Y")
        filepath = path.join(folder, datetime_obj.strftime("%d-%m-%Y"))
        # Generando el nombre del archivo que va a contener la información
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

        # Guardando la información en un archivo de tipo excel
        dataset.save_dataset(path.join(filepath, filename))
        log(
            INFO,
            f"Archivo {filename} de tipo {filetype} guardado correctamente en la ruta {filepath}",
        )

    def save_time_execution(self, filename, sheet_name):
        """Guarda la información del tiempo de ejecución del scraper

        Args:
            filename (str): Nombre del archivo
            sheet_name (str): Nombre de la hoja de cálculo
        """
        # Guardando los parametros finales del tiempo de ejecución del scraper
        self._time.set_param_final()
        log(INFO, "Guardando tiempos")
        # Variable que indica si el encabezados existe o no en el archivo de excel
        header_exist = True

        # Verificando si el archivo existe o no
        if path.isfile(filename):
            # Leendo el archivo
            wb_time = load_workbook(filename)
        else:
            # Creando un archivo de tipo workbook
            wb_time = Workbook()
            wb_time.worksheets[0].title = sheet_name
            header_exist = False

        # Comprobando si ya existe un sheet con el nombre indicado en la variable sheet_name
        if sheet_name not in [ws.title for ws in wb_time.worksheets]:
            # Creando un nuevo sheet
            wb_time.create_sheet(sheet_name)
            # Especificar que no existen encabezados en el nuevo sheet
            header_exist = False

        # Seleccionar el sheet deseado donde se va a guardar la información
        worksheet = wb_time[sheet_name]

        # Comprobando si el encabezados existen o no
        if not header_exist:
            # Lista que contiene los encabezados a ser insertados
            keys = [
                "Fecha",
                "Hora Inicio",
                "Hora Fin",
                "Cantidad",
                "Tiempo Ejecucion (min)",
                "Categorias / Minuto",
                "Errores",
            ]
            # Insertando los encabezados al worksheet
            worksheet.append(keys)

        # Lista que contiene los valores a ser insertados
        values = list(self._time.__dict__.values())[1:]
        # Insertando la información del tiempo al worksheet
        worksheet.append(values)
        # Guardar la información en un archivo excel
        wb_time.save(filename)
        # Cerrar el archivo excel
        wb_time.close()
        log(INFO, "Tiempos Guardados Correctamente")


def config_log(
    log_folder, log_filename, log_file_mode, log_file_encoding, current_date
):
    """Función que configura los logs para rastrear al programa

    Args:
        log_folder (str): Carpeta donde se va a generar el archivo log
        log_filename (str): Nombre del archivo log a ser generado
        log_file_mode (str): Modo de guardado del archivo
        log_file_encoding (str): Codificación usada para el archivo
        current_date (datetime): Fecha actual de la creación del archivo log
    """
    # Mostrar solo los errores de los registros que maneja selenium
    seleniumLogger.setLevel(ERROR)
    environ["WDM_LOG"] = "0"
    # Mostrar solo los errores de los registros que maneja urllib
    urllibLogger.setLevel(ERROR)
    # Generando la ruta donde se va a guardar los registros de ejecución
    log_path = path.join(log_folder, current_date.strftime("%d-%m-%Y"))
    # Generando el nombre del archivo que va a contener los registros de ejecución
    log_filename = log_filename + "_" + current_date.strftime("%d%m%Y") + ".log"
    # Verificando si la ruta donde se va a guardar los registros de ejecución existe
    if not path.exists(log_path):
        # Creando la ruta donde se va a guardar los registros de ejecución
        makedirs(log_path)

    # Configuración básica de los logs que maneja este programa
    basicConfig(
        format="%(asctime)s %(message)s",
        level=INFO,
        handlers=[
            StreamHandler(),
            FileHandler(
                path.join(log_path, log_filename), log_file_mode, log_file_encoding
            ),
        ],
    )


def validate_params(parameters):
    """Función que valida si los parámetros a usar están definidos

    Args:
        parameters (list): Lista de parámetros

    Returns:
        bool: Booleano que indica si los parámetros están definidos o no
    """
    for param in parameters:
        log(INFO, f"{param=}")
        # Verifica que el parámetro haya sido definido
        if not param or param == "":
            # Retorna false si algunos de los parámetros no fue definido
            return False

    # Retorna verdadero si todos los parámetros fueron definidos
    return True


def main():
    # Formato para el debugger
    current_date = datetime.now().date()
    config_log("Log", "fb_ropa_log", "w", "utf-8", current_date)
    log(INFO, "Configurando Formato Básico del Debugger")

    # Url de la tienda de saga falabella
    URL = "https://tienda.falabella.com.pe/falabella-pe"

    # Parámetros para guardar la data extraída por el scraper
    DATA_FILENAME = "falabella_category"
    DATA_FOLDER = "Data"

    # Parámetros para guardar la data extraída por el scraper a ser usada como diccionario de datos
    DATA_DICT_FILENAME = "example.csv"

    # Parámetros para guardar los errores durante la ejecución por el scraper
    ERROR_FILENAME = "falabella_error"
    ERROR_FOLDER = "Error"

    # Parámetros para guardar la medición de la ejecución del scraper
    TIME_FILENAME = "Tiempos.xlsx"
    TIME_SHEET_NAME = "Categorias"

    log(INFO, "Validando parámetros a usar")
    if not validate_params(
        [
            DATA_FILENAME,
            DATA_FOLDER,
            DATA_DICT_FILENAME,
            ERROR_FILENAME,
            ERROR_FOLDER,
            TIME_FILENAME,
            TIME_SHEET_NAME,
            URL,
        ]
    ):
        log(ERROR, "Parámetros incorrectos")
        return
    log(INFO, "Parámetros válidos")

    scraper = ScraperFalabellaCategory(current_date, DATA_DICT_FILENAME)

    # Entrando a la página web de la tienda de saga falabella
    scraper.enter_website(URL)

    # Maximizando la ventana del navegador
    scraper.maximize_window()

    # Cerrar ventanas emergentes molestas
    scraper.close_popups()

    # Extraer las categorías
    scraper.extract_categories(1)

    # Guardando la data extraída por el scraper
    scraper.save_data("Data", DATA_FOLDER, DATA_FILENAME)

    # Guardando los errores extraídos por el scraper
    scraper.save_data("Error", ERROR_FOLDER, ERROR_FILENAME)

    # Guardando los tiempos durante la ejecución del scraper
    scraper.save_time_execution(TIME_FILENAME, TIME_SHEET_NAME)
    log(INFO, "Programa finalizado")

    # Liberar el archivo log
    shutdown()


if __name__ == "__main__":
    main()
