import datetime
import re
import threading

import pytz
from django.contrib.auth.decorators import login_required

import simplejson as json
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import model_to_dict
from django.http import JsonResponse

from clients.models import CardBase, Individual, Card, Document, DocumentType, District, AnamnesisHistory, \
    DispensaryReg, CardDocUsage
from contracts.models import Company
from laboratory import settings
from laboratory.utils import strdate
from rmis_integration.client import Client
from slog.models import Log


def full_patient_search_data(p, query):
    dp = re.compile(r'^[0-9]{2}\.[0-9]{2}\.[0-9]{4}$')
    split = str(re.sub(' +', ' ', str(query))).split()
    n = p = ""
    f = split[0]
    rmis_req = {"surname": f + "%"}
    if len(split) > 1:
        n = split[1]
        rmis_req["name"] = n + "%"
    if len(split) > 2:
        if re.search(dp, split[2]):
            split = [split[0], split[1], '', split[2]]
        else:
            p = split[2]
            rmis_req["patrName"] = p + "%"
    if len(split) > 3:
        btday = split[3].split(".")
        btday = btday[2] + "-" + btday[1] + "-" + btday[0]
        rmis_req["birthDate"] = btday
    return f, n, p, rmis_req, split


@login_required
def patients_search_card(request):
    objects = []
    data = []
    d = json.loads(request.body)
    inc_rmis = d.get('inc_rmis')
    card_type = CardBase.objects.get(pk=d['type'])
    query = d['query'].strip()
    p = re.compile(r'[а-яё]{3}[0-9]{8}', re.IGNORECASE)
    p2 = re.compile(r'^([А-яЁё\-]+)( ([А-яЁё\-]+)(( ([А-яЁё\-]*))?( ([0-9]{2}\.[0-9]{2}\.[0-9]{4}))?)?)?$')
    p3 = re.compile(r'^[0-9]{1,15}$')
    p4 = re.compile(r'card_pk:\d+', flags=re.IGNORECASE)
    p4i = bool(re.search(p4, query.lower()))
    pat_bd = re.compile(r"\d{4}-\d{2}-\d{2}")
    c = None
    if not p4i:
        if re.search(p, query.lower()):
            initials = query[0:3].upper()
            btday = query[7:11] + "-" + query[5:7] + "-" + query[3:5]
            if not pat_bd.match(btday):
                return JsonResponse([], safe=False)
            try:
                objects = Individual.objects.filter(family__startswith=initials[0], name__startswith=initials[1],
                                                    patronymic__startswith=initials[2], birthday=btday,
                                                    card__base=card_type)
                if (card_type.is_rmis and len(objects) == 0) or (card_type.internal_type and inc_rmis):
                    c = Client(modules="patients")
                    objects = c.patients.import_individual_to_base(
                        {"surname": query[0] + "%", "name": query[1] + "%", "patrName": query[2] + "%",
                         "birthDate": btday},
                        fio=True)
            except ValidationError:
                objects = []
        elif re.search(p2, query):
            f, n, p, rmis_req, split = full_patient_search_data(p, query)
            objects = Individual.objects.filter(family__istartswith=f, name__istartswith=n,
                                                patronymic__istartswith=p, card__base=card_type)[:10]
            if len(split) > 3:
                objects = Individual.objects.filter(family__istartswith=f, name__istartswith=n,
                                                    patronymic__istartswith=p, card__base=card_type,
                                                    birthday=datetime.datetime.strptime(split[3], "%d.%m.%Y").date())[
                          :10]

            if (card_type.is_rmis and (len(objects) == 0 or (len(split) < 4 and len(objects) < 10))) \
                    or (card_type.internal_type and inc_rmis):
                objects = list(objects)
                try:
                    if not c:
                        c = Client(modules="patients")
                    objects += c.patients.import_individual_to_base(rmis_req, fio=True, limit=10 - len(objects))
                except ConnectionError:
                    pass

        if (re.search(p3, query) and not card_type.is_rmis) \
                or (len(list(objects)) == 0 and len(query) == 16 and card_type.internal_type) \
                or (card_type.is_rmis and not re.search(p3, query)):
            resync = True
            if len(list(objects)) == 0:
                resync = False
                try:
                    objects = Individual.objects.filter(card__number=query.upper(), card__is_archive=False,
                                                        card__base=card_type)
                except ValueError:
                    pass
                if (card_type.is_rmis or card_type.internal_type) and len(list(objects)) == 0 and len(query) == 16:
                    if not c:
                        c = Client(modules="patients")
                    objects = c.patients.import_individual_to_base(query)
                else:
                    resync = True
            if resync and card_type.is_rmis:
                if not c:
                    c = Client(modules="patients")

                sema = threading.BoundedSemaphore(10)
                threads = list()

                def sync_i(o: Individual, client: Client):
                    sema.acquire()
                    try:
                        o.sync_with_rmis(c=client)
                    finally:
                        sema.release()

                for o in objects:
                    thread = threading.Thread(target=sync_i, args=(o, c))
                    threads.append(thread)
                    thread.start()

    if p4i:
        cards = Card.objects.filter(pk=int(query.split(":")[1]))
    else:
        cards = Card.objects.filter(base=card_type, individual__in=objects, is_archive=False)
        if re.match(p3, query):
            cards = cards.filter(number=query)

    for row in cards.filter(is_archive=False).prefetch_related("individual").distinct():
        docs = Document.objects.filter(individual__pk=row.individual.pk, is_active=True,
                                       document_type__title__in=['СНИЛС', 'Паспорт гражданина РФ', 'Полис ОМС']) \
            .distinct("pk", "number", "document_type", "serial").order_by('pk')
        data.append({"type_title": card_type.title,
                     "num": row.number,
                     "is_rmis": row.base.is_rmis,
                     "family": row.individual.family,
                     "name": row.individual.name,
                     "twoname": row.individual.patronymic,
                     "birthday": row.individual.bd(),
                     "age": row.individual.age_s(),
                     "fio_age": row.individual.fio(full=True),
                     "sex": row.individual.sex,
                     "individual_pk": row.individual.pk,
                     "pk": row.pk,
                     "phones": row.get_phones(),
                     "main_diagnosis": row.main_diagnosis,
                     "docs": [{**model_to_dict(x), "type_title": x.document_type.title} for x in docs]})
    return JsonResponse({"results": data})


@login_required
def patients_search_individual(request):
    objects = []
    data = []
    d = json.loads(request.body)
    query = d['query'].strip()
    p = re.compile(r'[а-яё]{3}[0-9]{8}', re.IGNORECASE)
    p2 = re.compile(r'^([А-яЁё\-]+)( ([А-яЁё\-]+)(( ([А-яЁё\-]*))?( ([0-9]{2}\.[0-9]{2}\.[0-9]{4}))?)?)?$')
    p4 = re.compile(r'individual_pk:\d+')
    pat_bd = re.compile(r"\d{4}-\d{2}-\d{2}")
    if re.search(p, query.lower()):
        initials = query[0:3].upper()
        btday = query[7:11] + "-" + query[5:7] + "-" + query[3:5]
        if not pat_bd.match(btday):
            return JsonResponse([], safe=False)
        try:
            objects = Individual.objects.filter(family__startswith=initials[0], name__startswith=initials[1],
                                                patronymic__startswith=initials[2], birthday=btday)
        except ValidationError:
            objects = []
    elif re.search(p2, query):
        f, n, p, rmis_req, split = full_patient_search_data(p, query)
        objects = Individual.objects.filter(family__istartswith=f, name__istartswith=n, patronymic__istartswith=p)
        if len(split) > 3:
            objects = Individual.objects.filter(family__istartswith=f, name__istartswith=n,
                                                patronymic__istartswith=p,
                                                birthday=datetime.datetime.strptime(split[3], "%d.%m.%Y").date())

    if re.search(p4, query):
        objects = Individual.objects.filter(pk=int(query.split(":")[1]))
    n = 0

    if not isinstance(objects, list):
        for row in objects.distinct().order_by("family", "name", "patronymic", "birthday"):
            n += 1
            data.append({"family": row.family,
                         "name": row.name,
                         "patronymic": row.patronymic,
                         "birthday": row.bd(),
                         "age": row.age_s(),
                         "sex": row.sex,
                         "pk": row.pk})
            if n == 25:
                break
    return JsonResponse({"results": data})


def patients_search_l2_card(request):
    data = []
    request_data = json.loads(request.body)

    cards = Card.objects.filter(pk=request_data.get('card_pk', -1))
    if cards.exists():
        card_orig = cards[0]
        Card.add_l2_card(card_orig=card_orig)
        l2_cards = Card.objects.filter(individual=card_orig.individual, base__internal_type=True)

        for row in l2_cards.filter(is_archive=False):
            docs = Document.objects.filter(individual__pk=row.individual.pk, is_active=True,
                                           document_type__title__in=['СНИЛС', 'Паспорт гражданина РФ', 'Полис ОМС']) \
                .distinct("pk", "number", "document_type", "serial").order_by('pk')
            data.append({"type_title": row.base.title,
                         "num": row.number,
                         "is_rmis": row.base.is_rmis,
                         "family": row.individual.family,
                         "name": row.individual.name,
                         "twoname": row.individual.patronymic,
                         "birthday": row.individual.bd(),
                         "age": row.individual.age_s(),
                         "sex": row.individual.sex,
                         "individual_pk": row.individual.pk,
                         "base_pk": row.base.pk,
                         "pk": row.pk,
                         "phones": row.get_phones(),
                         "docs": [{**model_to_dict(x), "type_title": x.document_type.title} for x in docs],
                         "main_diagnosis": row.main_diagnosis})
    return JsonResponse({"results": data})


def patients_get_card_data(request, card_id):
    card = Card.objects.get(pk=card_id)
    c = model_to_dict(card)
    i = model_to_dict(card.individual)
    docs = [{**model_to_dict(x), "type_title": x.document_type.title}
            for x in Document.objects.filter(individual=card.individual).distinct('pk', "number", "document_type",
                                                                                  "serial").order_by('pk')]
    rc = Card.objects.filter(base__is_rmis=True, individual=card.individual)
    d = District.objects.all().order_by('-sort_weight', '-id')
    return JsonResponse({**i, **c,
                         "docs": docs,
                         "main_docs": card.get_card_documents(),
                         "has_rmis_card": rc.exists(),
                         "av_companies": [{"id": -1, "title": "НЕ ВЫБРАНО", "short_title": ""},
                                          *[model_to_dict(x) for x in
                                            Company.objects.filter(active_status=True).order_by('title')]],
                         "custom_workplace": card.work_place != "",
                         "work_place_db": card.work_place_db.pk if card.work_place_db else -1,
                         "district": card.district_id or -1,
                         "districts": [{"id": -1, "title": "НЕ ВЫБРАН"},
                                       *[{"id": x.pk, "title": x.title} for x in d.filter(is_ginekolog=False)]],
                         "ginekolog_district": card.ginekolog_district_id or -1,
                         "gin_districts": [{"id": -1, "title": "НЕ ВЫБРАН"},
                                           *[{"id": x.pk, "title": x.title} for x in d.filter(is_ginekolog=True)]],
                         "agent_types": [{"key": x[0], "title": x[1]} for x in Card.AGENT_CHOICES if x[0]],
                         "excluded_types": Card.AGENT_CANT_SELECT,
                         "agent_need_doc": Card.AGENT_NEED_DOC,
                         "mother": None if not card.mother else card.mother.get_fio_w_card(),
                         "mother_pk": None if not card.mother else card.mother.pk,
                         "father": None if not card.father else card.father.get_fio_w_card(),
                         "father_pk": None if not card.father else card.father.pk,
                         "curator": None if not card.curator else card.curator.get_fio_w_card(),
                         "curator_pk": None if not card.curator else card.curator.pk,
                         "agent": None if not card.agent else card.agent.get_fio_w_card(),
                         "agent_pk": None if not card.agent else card.agent.pk,
                         "payer": None if not card.payer else card.payer.get_fio_w_card(),
                         "payer_pk": None if not card.payer else card.payer.pk,
                         "rmis_uid": rc[0].number if rc.exists() else None,
                         "doc_types": [{"pk": x.pk, "title": x.title} for x in DocumentType.objects.all()]})


def patients_card_save(request):
    request_data = json.loads(request.body)
    result = "fail"
    message = ""
    card_pk = -1
    individual_pk = -1

    if "new_individual" in request_data and (
            request_data["new_individual"] or not Individual.objects.filter(pk=request_data["individual_pk"])) and \
            request_data["card_pk"] < 0:
        i = Individual(family=request_data["family"],
                       name=request_data["name"],
                       patronymic=request_data["patronymic"],
                       birthday=request_data["birthday"],
                       sex=request_data["sex"])
        i.save()
    else:
        changed = False
        i = Individual.objects.get(
            pk=request_data["individual_pk"] if request_data["card_pk"] < 0 else Card.objects.get(
                pk=request_data["card_pk"]).individual.pk)
        if i.family != request_data["family"] \
                or i.name != request_data["name"] \
                or i.patronymic != request_data["patronymic"] \
                or str(i.birthday) != request_data["birthday"] \
                or i.sex != request_data["sex"]:
            changed = True
        i.family = request_data["family"]
        i.name = request_data["name"]
        i.patronymic = request_data["patronymic"]
        i.birthday = request_data["birthday"]
        i.sex = request_data["sex"]
        i.save()
        if Card.objects.filter(individual=i, base__is_rmis=True).exists() and changed:
            c = Client(modules=["individuals", "patients"])
            c.patients.send_patient(Card.objects.filter(individual=i, base__is_rmis=True)[0])

    individual_pk = i.pk

    if request_data["card_pk"] < 0:
        base = CardBase.objects.get(pk=request_data["base_pk"], internal_type=True)
        last_l2 = Card.objects.filter(base__internal_type=True).extra(
            select={'numberInt': 'CAST(number AS INTEGER)'}
        ).order_by("-numberInt").first()
        n = 0
        if last_l2:
            n = int(last_l2.number)
        c = Card(number=n + 1, base=base,
                 individual=i,
                 main_diagnosis="", main_address="",
                 fact_address="")
        c.save()
        card_pk = c.pk
        Log.log(card_pk, 30000, request.user.doctorprofile, request_data)
    else:
        card_pk = request_data["card_pk"]
        c = Card.objects.get(pk=card_pk)
        individual_pk = request_data["individual_pk"]
        Log.log(card_pk, 30001, request.user.doctorprofile, request_data)
    c.main_diagnosis = request_data["main_diagnosis"]
    c.main_address = request_data["main_address"]
    c.fact_address = request_data["fact_address"]
    if request_data["custom_workplace"] or not Company.objects.filter(pk=request_data["work_place_db"]).exists():
        c.work_place_db = None
        c.work_place = request_data["work_place"]
    else:
        c.work_place_db = Company.objects.get(pk=request_data["work_place_db"])
        c.work_place = ''
    c.district_id = request_data["district"] if request_data["district"] != -1 else None
    c.ginekolog_district_id = request_data["gin_district"] if request_data["gin_district"] != -1 else None
    c.work_position = request_data["work_position"]
    c.phone = request_data["phone"]
    c.save()
    if c.individual.primary_for_rmis:
        c.individual.sync_with_rmis()
    result = "ok"
    return JsonResponse({"result": result, "message": message, "card_pk": card_pk, "individual_pk": individual_pk})


def individual_search(request):
    result = []
    request_data = json.loads(request.body)
    for i in Individual.objects.filter(**request_data):
        result.append({
            "pk": i.pk,
            "fio": i.fio(full=True),
            "docs": [
                {**model_to_dict(x), "type_title": x.document_type.title}
                for x in Document.objects.filter(individual=i, is_active=True)
                    .distinct("number", "document_type", "serial", "date_end", "date_start")
            ],
            "l2_cards": [
                x.number for x in Card.objects.filter(individual=i, base__internal_type=True, is_archive=False)
            ],
        })
    return JsonResponse({"result": result})


def get_sex_by_param(request):
    request_data = json.loads(request.body)
    t = request_data.get("t")
    v = request_data.get("v", "")
    r = "м"
    if t == "name":
        p = Individual.objects.filter(name=v)
        r = "м" if p.filter(sex__iexact="м").count() >= p.filter(sex__iexact="ж").count() else "ж"
    if t == "family":
        p = Individual.objects.filter(family=v)
        r = "м" if p.filter(sex__iexact="м").count() >= p.filter(sex__iexact="ж").count() else "ж"
    if t == "patronymic":
        p = Individual.objects.filter(patronymic=v)
        r = "м" if p.filter(sex__iexact="м").count() >= p.filter(sex__iexact="ж").count() else "ж"
    return JsonResponse({"sex": r})


def edit_doc(request):
    request_data = json.loads(request.body)
    pk = request_data["pk"]
    serial = request_data["serial"]
    number = request_data["number"]
    type_o = DocumentType.objects.get(pk=request_data["type"])
    is_active = request_data["is_active"]
    date_start = request_data["date_start"]
    date_start = None if date_start == "" else date_start
    date_end = request_data["date_end"]
    date_end = None if date_end == "" else date_end
    who_give = request_data["who_give"] or ""

    if pk == -1:
        card = Card.objects.get(pk=request_data["card_pk"])
        d = Document(document_type=type_o, number=number, serial=serial, from_rmis=False, date_start=date_start,
                     date_end=date_end, who_give=who_give, is_active=is_active,
                     individual=Individual.objects.get(pk=request_data["individual_pk"]))
        d.save()
        cdu = CardDocUsage.objects.filter(card=card, document__document_type=type_o)
        if not cdu.exists():
            CardDocUsage(card=card, document=d).save()
        else:
            cdu.update(document=d)
        Log.log(d.pk, 30002, request.user.doctorprofile, request_data)
    else:
        Document.objects.filter(pk=pk, from_rmis=False).update(number=number, serial=serial,
                                                               is_active=is_active, date_start=date_start,
                                                               date_end=date_end, who_give=who_give)
        Log.log(pk, 30002, request.user.doctorprofile, request_data)
        d = Document.objects.get(pk=pk)
    d.sync_rmis()

    return JsonResponse({"ok": True})


def update_cdu(request):
    request_data = json.loads(request.body)
    card = Card.objects.get(pk=request_data["card_pk"])
    doc = Document.objects.get(pk=request_data["doc_pk"])
    cdu = CardDocUsage.objects.filter(card=card, document__document_type=doc.document_type)
    if not cdu.exists():
        CardDocUsage(card=card, document=doc).save()
    else:
        cdu.update(document=doc)
    Log.log(card.pk, 30004, request.user.doctorprofile, request_data)

    return JsonResponse({"ok": True})


def sync_rmis(request):
    request_data = json.loads(request.body)
    card = Card.objects.get(pk=request_data["card_pk"])
    card.individual.sync_with_rmis()
    return JsonResponse({"ok": True})


def update_wia(request):
    request_data = json.loads(request.body)
    card = Card.objects.get(pk=request_data["card_pk"])
    key = request_data["key"]
    if key in [x[0] for x in Card.AGENT_CHOICES]:
        card.who_is_agent = key
        card.save()
        Log.log(card.pk, 30006, request.user.doctorprofile, request_data)

    return JsonResponse({"ok": True})


def edit_agent(request):
    request_data = json.loads(request.body)
    key = request_data["key"]
    card = None if not request_data["card_pk"] else Card.objects.get(pk=request_data["card_pk"])
    parent_card = Card.objects.filter(pk=request_data["parent_card_pk"])
    doc = request_data["doc"] or ''
    clear = request_data["clear"]
    need_doc = key in Card.AGENT_NEED_DOC

    upd = {}

    if clear or not card:
        upd[key] = None
        if need_doc:
            upd[key + "_doc_auth"] = ''
        if parent_card[0].who_is_agent == key:
            upd["who_is_agent"] = ''
    else:
        upd[key] = card
        if need_doc:
            upd[key + "_doc_auth"] = doc
        if not key in Card.AGENT_CANT_SELECT:
            upd["who_is_agent"] = key

    parent_card.update(**upd)

    Log.log(parent_card.pk, 30005, request.user.doctorprofile, request_data)

    return JsonResponse({"ok": True})


def load_dreg(request):
    request_data = json.loads(request.body)
    data = []
    for a in DispensaryReg.objects.filter(card__pk=request_data["card_pk"]).order_by('date_start', 'pk'):
        data.append({
            "pk": a.pk,
            "diagnos": a.diagnos,
            "illnes": a.illnes,
            "spec_reg": '' if not a.spec_reg else a.spec_reg.title,
            "doc_start_reg": '' if not a.doc_start_reg else a.doc_start_reg.get_fio(),
            "doc_start_reg_id": a.doc_start_reg_id,
            "date_start": '' if not a.date_start else strdate(a.date_start),
            "doc_end_reg": '' if not a.doc_end_reg else a.doc_end_reg.get_fio(),
            "doc_end_reg_id": a.doc_end_reg_id,
            "date_end": '' if not a.date_end else strdate(a.date_end),
            "why_stop": a.why_stop,
        })
    return JsonResponse({"rows": data})


def load_dreg_detail(request):
    a = DispensaryReg.objects.get(pk=json.loads(request.body)["pk"])
    data = {
        "diagnos": a.diagnos + ' ' + a.illnes,
        "date_start": None if not a.date_start else a.date_start,
        "date_end": None if not a.date_end else a.date_end,
        "close": bool(a.date_end),
        "why_stop": a.why_stop,
    }
    return JsonResponse(data)


@transaction.atomic
def save_dreg(request):
    rd = json.loads(request.body)
    d = rd["data"]
    pk = rd["pk"]
    n = False
    if pk == -1:
        a = DispensaryReg.objects.create(card_id=rd["card_pk"])
        pk = a.pk
        n = True
    else:
        pk = rd["pk"]
        a = DispensaryReg.objects.get(pk=pk)

    Log.log(pk, 40000 if n else 40001, request.user.doctorprofile, rd)

    c = False

    def fd(s):
        if '.' in s:
            s = s.split('.')
            s = '{}-{}-{}'.format(s[2], s[1], s[0])
        return s

    if not a.date_start and d["date_start"] \
            or str(a.date_start) != fd(d["date_start"]) \
            or a.spec_reg != request.user.doctorprofile.specialities \
            or a.doc_start_reg != request.user.doctorprofile:
        a.date_start = fd(d["date_start"])
        a.doc_start_reg = request.user.doctorprofile
        a.spec_reg = request.user.doctorprofile.specialities
        c = True

    if not a.date_end and d["close"] \
            or (d["close"] and str(a.date_end) != fd(d["date_end"])):
        a.date_end = fd(d["date_end"])
        a.why_stop = d["why_stop"]
        a.doc_end_reg = request.user.doctorprofile
        c = True
    elif d["close"] and a.why_stop != d["why_stop"]:
        a.why_stop = d["why_stop"]
        c = True

    if not d["close"] and (a.date_end or a.why_stop):
        a.date_end = None
        a.why_stop = ''
        a.doc_end_reg = None
        c = True

    i = d["diagnos"].split(' ')
    ds = i.pop(0)
    if len(i) == 0:
        i = ''
    else:
        i = ' '.join(i)

    if a.diagnos != ds or a.illnes != i:
        a.diagnos = ds
        a.illnes = i
        c = True

    if c:
        a.save()

    return JsonResponse({"ok": True, "pk": pk, "c": c})


def load_anamnesis(request):
    request_data = json.loads(request.body)
    card = Card.objects.get(pk=request_data["card_pk"])
    history = []
    for a in AnamnesisHistory.objects.filter(card=card).order_by('-pk'):
        history.append({
            "pk": a.pk,
            "text": a.text,
            "who_save": {
                "fio": a.who_save.get_fio(dots=True),
                "department": a.who_save.podrazdeleniye.get_title(),
            },
            "datetime": a.created_at.astimezone(pytz.timezone(settings.TIME_ZONE)).strftime("%d.%m.%Y %X"),
        })
    data = {
        "text": card.anamnesis_of_life,
        "history": history,
    }
    return JsonResponse(data)


def save_anamnesis(request):
    request_data = json.loads(request.body)
    card = Card.objects.get(pk=request_data["card_pk"])
    if card.anamnesis_of_life != request_data["text"]:
        card.anamnesis_of_life = request_data["text"]
        card.save()
        AnamnesisHistory(card=card, text=request_data["text"], who_save=request.user.doctorprofile).save()
    return JsonResponse({"ok": True})