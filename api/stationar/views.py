from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from clients.models import Card
from directions.models import Issledovaniya, Napravleniya
from laboratory.decorators import group_required
import simplejson as json
from utils import tree_directions


@login_required
@group_required("Врач стационара")
def load(request):
    data = json.loads(request.body)
    result = {"ok": False, "message": "Нет данных", "data": {}}
    pk = int(data["pk"])
    if pk >= 4600000000000:
        pk -= 4600000000000
        pk //= 10
    for i in Issledovaniya.objects.filter(napravleniye__pk=pk, research__is_hospital=True):
        direction: Napravleniya = i.napravleniye
        card: Card = direction.client
        result["ok"] = True
        result["message"] = ""
        result["data"] = {
            "direction": direction.pk,
            "patient": {
                "fio_age": card.individual.fio(full=True),
                "card": card.number_with_type(),
                "base": card.base_id,
                "card_pk": card.pk,
                "individual_pk": card.individual_id,
            }
        }
        break
    return JsonResponse(result)


def hosp_get_data_direction(main_direction, site_type=-1, type_service='None', level=-1):
    # получить данные по разделу Стационарной карты
    # hosp_site_type=-1 - не получать ничего.
    # level уровень подчинения. Если вернуть только дочерние для текущего направления level=2
    result = tree_directions.get_research_by_dir(main_direction)
    num_iss = result[0][0]
    main_research = result[0][1]

    hosp_site_type = site_type
    hosp_level = level
    hosp_is_paraclinic, hosp_is_doc_refferal, hosp_is_lab, hosp_is_hosp = False, False, False, False
    if type_service == 'is_paraclinic':
        hosp_is_paraclinic = True
    elif type_service == 'is_doc_refferal':
        hosp_is_doc_refferal = True
    elif type_service == 'is_lab':
        hosp_is_lab = True

    hosp_dirs = tree_directions.hospital_get_direction(num_iss, main_research, hosp_site_type, hosp_is_paraclinic,
                                                       hosp_is_doc_refferal, hosp_is_lab, hosp_is_hosp, hosp_level)

    data = []
    if hosp_dirs:
        for i in hosp_dirs:
            data.append({'direction' : i[0], 'date_create' : i[1], 'time_create' : i[2], 'iss' : i[5], 'date_confirm' : i[6],
                         'time_confirm' : i[7], 'research_id' : i[8], 'research_title' : i[9], 'podrazdeleniye_id' : i[13],
                         'is_paraclinic' : i[14], 'is_doc_refferal' : i[15], 'is_stom' : i[16], 'is_hospital' : i[17],
                         'is_microbiology' : i[18], 'podrazdeleniye_title' : i[19], 'site_type' : i[21]})

    return data


def hosp_get_hosp_direction(num_dir):
    #возвращает дерево направлений-отделений, у к-рых тип улуги только is_hosp
    #[{'direction': номер направления, 'research_title': значение}, {'direction': номер направления, 'research_title': значение}]
    root_dir = tree_directions.root_direction(num_dir)
    num_root_dir = root_dir[-1][-3]
    result = tree_directions.get_research_by_dir(num_root_dir)
    num_iss = result[0][0]
    main_research = result[0][1]
    hosp_site_type = -1
    hosp_is_paraclinic, hosp_is_doc_refferal, hosp_is_lab = False, False, False
    hosp_is_hosp = True
    hosp_level = -1
    hosp_dirs = tree_directions.hospital_get_direction(num_iss, main_research, hosp_site_type, hosp_is_paraclinic,
                                                       hosp_is_doc_refferal, hosp_is_lab, hosp_is_hosp, hosp_level)

    for i in hosp_dirs:
        print(i)
    data = [{'direction' : i[0], 'research_title' : i[9]} for i in hosp_dirs]

    return data


def hosp_get_curent_hosp_dir(current_iss):
    iss_obj = Issledovaniya.objects.values('napravleniye_id').filter(pk=current_iss)
    num_dir = iss_obj[0]['napravleniye_id']
    obj_dir = Napravleniya.objects.filter(pk=num_dir).first()
    hosp_dir = obj_dir.parent.napravleniye_id
    return hosp_dir


def hosp_get_lab_iss(current_iss, extract=False):
    """
    агрегация результатов исследований
    возврат:  Если extract=True(выписка), то берем по всем hosp-dirs. Если эпикриз, то берем все исследования
    до текущего hosp-dirs"""

    iss_obj = Issledovaniya.objects.values('napravleniye_id').filter(pk=current_iss)
    num_dir = iss_obj[0]['napravleniye_id']

    #получить все направления в истории по типу hosp
    hosp_dirs = hosp_get_hosp_direction(num_dir)

    #получить текущее направление типа hosp из текущего эпикриза
    current_dir = hosp_get_curent_hosp_dir(current_iss)

    if not extract:
        hosp_dirs = [i for i in hosp_dirs if i < current_dir]

    #получить исследования лаб. для КДЛ, Биохимии, Иммунологии каждое по vertical_result_display по направлениям типа hosp



    # получить результаты фракци по исследованиям
