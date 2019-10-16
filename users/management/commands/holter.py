from django.core.management import BaseCommand



import pdfkit
import os, datetime
# pdfkit.from_file('c:\\my\\node_project\\holter\\ME1747190927113306.001\\ME1747190927113306.html', 'c:/tmp/holter24.pdf')
# path = 'c:\\my\\node_project\\holter\\ME1747190927113306.001\\ME1747190927113306.html'
# a = os.path.getmtime(path)
#2019-09-30 22:11:51.790084
# print(datetime.datetime.fromtimestamp(a))

import  pathlib, sys, time
# p = pathlib.Path('c:\\my\\node_project\\holter\\ME1747190927113306.001\\ME1747190927113306.html')
# p = pathlib.Path('c:\\my\\node_project\\holter\\ME1747190927113306.001\\')
# stat_info = p.stat()
# print(f'{p}')
# print(f"Size: {stat_info.st_size}")
# print(f"created: {time.ctime(stat_info.st_ctime)}")
# print(f"modify: {time.ctime(stat_info.st_mtime)}")
# print(f"acces: {time.ctime(stat_info.st_atime)}")
# print(f"acces: {time.ctime(stat_info.st_atime)}")

##################################################
# в каталогах созданных -20 дней назад
# найти файлы *.html дата изменния к-рые больше заданной(из базы)
# Если такой ф-л найден и размер > 30кБайт:
  # то попытаться найти в нем последовательность цифр направления из Адрес: <b>5555555557778978978</b>
    #если найдена, то проверить, что такое направление существует в L2 и оно не подтверждено, или
                   #подтверждено, но разница от дата подтверждения и текущей не более 48 часов
      #если условия, удовлетворены, то:
        #проверить путь на наличие директории ../год/месяц/число (дата из св-ва ф-ла модификации)
        #если нет каталога, то создать директорию:
          #потом сгенерировать с помощью pdfkit ф-л с названием: номер направления и ФИО-пациента (4600000121Иванов) и
          #сохранить в каталог путь ../год/месяц/число/4600000121Иванов.pdf
          #записать ссылку на ф-л на результат в спец поле в L2
          #если найдена последовательность Врач: Фамилия
              #подтвердить результат от имени врача
          #Если нет, то от имени зав.отд.
import pathlib, re
from datetime import datetime
from dateutil.relativedelta import *
from directions.models import Issledovaniya, Napravleniya
from appconf.manager import SettingManager
from users.models import DoctorProfile
from shutil import copytree, rmtree
from integration_framework.models import TempData
from laboratory.settings import TIME_ZONE
from django.utils.timezone import now, pytz

class Command(BaseCommand):
    help = "Обработка холтера"

    def handle(self, *args, **options):
        dst_dir = SettingManager.get("root_dir")
        src_dir = SettingManager.get("src_holter")
        p = pathlib.Path(src_dir)
        temp_dir = SettingManager.get("temp_dir")

        #в каих каталогах искать "-" дней
        day_count = 10
        today_dir = datetime.now().strftime('%Y/%m/%d')
        d_start = datetime.now().date() - relativedelta(days=day_count)
        #Ищем последовательность
        pattern = re.compile('(Направление: <b>\d+</b>;)|(Адрес: <b>\d+</b>;)')
        pattern_doc = re.compile('Врач')

        #услуга относящаяся к подразделению
        podrazdeleniye_pk = 85
        podrazdeleniye_users = DoctorProfile.objects.values_list('pk', 'fio').filter(podrazdeleniye=podrazdeleniye_pk)
        podrazdeleniye_manager_pk=1108

        date_time = '2019-09-01 10:48:07.558120'
        holter_obj, created = TempData.objects.get_or_create(key='holter', defaults={"holter_protocol_date": date_time})
        user_timezone = pytz.timezone(TIME_ZONE)

        if created:
            date_proto = TempData.objects.values_list('holter_protocol_date').get(key='holter')
        else:
            date_proto = holter_obj.holter_protocol_date
        print('##', date_proto.astimezone(user_timezone))

        doctors = {}
        for i in podrazdeleniye_users:
            k = i[1].split()
            temp_dict = {k[0] : i[0]}
            doctors.update(temp_dict)


        for f in p.iterdir():
            stat_info = f.stat()
            if datetime.fromtimestamp(stat_info.st_ctime) > datetime.combine(d_start, datetime.min.time()):
                for h in f.glob('*.html'):
                    find = False

                    stat_info = h.stat()
                    file_modify = datetime.fromtimestamp(stat_info.st_mtime).astimezone(user_timezone)
                    holter_path_result = h.as_posix()
                    file_name = holter_path_result.split('/')[-1]

                    if stat_info.st_size > 30000 and file_modify >= date_proto:
                        with open(holter_path_result) as file:
                            for line in file:
                                result = pattern.match(line)
                                if result:
                                    obj_num_dir = re.search(r'\d+', result.group(0))
                                    num_dir = obj_num_dir.group(0)
                                    print(num_dir)
                                    obj_iss = Issledovaniya.objects.filter(napravleniye=num_dir, research=298).first()
                                    if obj_iss:
                                        patient = Napravleniya.objects.filter(pk=num_dir).first()
                                        fio = patient.client.get_fio_w_card()
                                        if not os.path.exists(dst_dir + today_dir):
                                            x = dst_dir + today_dir
                                            os.makedirs(x)
                                        find = True
                                        current_dir = os.path.dirname(holter_path_result)
                                        file_modify = datetime.fromtimestamp(stat_info.st_mtime).astimezone(user_timezone)
                                        TempData.objects.filter(key='holter').update(holter_protocol_date=file_modify)

                                        if os.path.exists(temp_dir):
                                            rmtree(temp_dir)
                                        copytree(current_dir, temp_dir)
                        if find:
                            with open(temp_dir + file_name, 'r') as f:
                                old_data = f.read()
                            new_data2 = old_data.replace('Адрес:', 'Направление:')
                            new_data = new_data2.replace('офд<o:p></o:p>', 'офд<o:p> ' + fio + '</o:p>')
                            with open(temp_dir + file_name, 'w') as f:
                                f.write(new_data)

                            with open(temp_dir + file_name, 'r') as f:
                                find_doc = False
                                exit = False
                                pk_doc = None
                                for line in f:
                                    result = pattern_doc.search(line)
                                    if result:
                                        find_doc = True
                                    if find_doc:
                                        for doc in doctors.keys():
                                            doc_fio_find = re.search(doc, line)
                                            if doc_fio_find:
                                                pk_doc = doctors.get(doc_fio_find.group(0))
                                                exit = True
                                                break
                                        if exit:
                                            break

                            list_fio = fio.split()
                            link = today_dir + f'/{num_dir + "_" + list_fio[2]}.pdf'
                            pdfkit.from_file(temp_dir + file_name, dst_dir + link)
                            if pk_doc:
                                doc_profile = DoctorProfile.objects.filter(pk=pk_doc).first()
                            else:
                                doc_profile = DoctorProfile.objects.filter(pk=podrazdeleniye_manager_pk).first()


                            obj_iss.doc_confirmation = doc_profile
                            obj_iss.link_file = today_dir + f'/{num_dir + "_" + list_fio[2]}.pdf'
                            obj_iss.save(update_fields=['doc_confirmation','link_file'])
                            rmtree(temp_dir)
