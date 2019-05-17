from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
import simplejson as json

from slog.models import Log
import users.models as users
from directory.models import Researches as DResearches, AutoAdd, ParaclinicInputGroups, Fractions, \
    ParaclinicTemplateName, ParaclinicInputField, ParaclinicTemplateField
from laboratory.decorators import group_required
from podrazdeleniya.models import Podrazdeleniya


class ResearchesTemplates(View):
    def get(self, request):
        from django.db.models import Q

        templates = []
        for t in users.AssignmentTemplates.objects.filter(global_template=True) \
                .filter(Q(doc__isnull=True, podrazdeleniye__isnull=True) |
                        Q(doc=request.user.doctorprofile) |
                        Q(podrazdeleniye=request.user.doctorprofile.podrazdeleniye)):
            templates.append({"values": [x.research.pk for x in users.AssignmentResearches.objects.filter(template=t)],
                              "pk": t.pk,
                              "title": t.title,
                              "for_current_user": t.doc is not None,
                              "for_users_department": t.podrazdeleniye is not None})
        return JsonResponse({"templates": templates})

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(self.__class__, self).dispatch(request, *args, **kwargs)


class Researches(View):
    def get(self, request):
        deps = defaultdict(list)

        for r in DResearches.objects.filter(hide=False).order_by("title"):
            autoadd = [x.b.pk for x in AutoAdd.objects.filter(a=r)]
            addto = [x.a.pk for x in AutoAdd.objects.filter(b=r)]

            deps[r.reversed_type].append(
                {"pk": r.pk,
                 "onlywith": -1 if not r.onlywith else r.onlywith.pk,
                 "department_pk": r.reversed_type,
                 "title": r.get_title(),
                 "full_title": r.title,
                 "doc_refferal": r.is_doc_refferal,
                 "treatment": r.is_treatment,
                 "stom": r.is_stom,
                 "need_vich_code": r.need_vich_code,
                 "comment_variants": [] if not r.comment_variants else r.comment_variants.get_variants(),
                 "autoadd": autoadd,
                 "addto": addto,
                 "code": r.code,
                 "type": "4" if not r.podrazdeleniye else str(r.podrazdeleniye.p_type),
                 "site_type": r.site_type.pk if r.site_type else None
                 })
        return JsonResponse({"researches": deps})

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(self.__class__, self).dispatch(request, *args, **kwargs)


@login_required
@group_required("Оператор", "Конструктор: Параклинические (описательные) исследования")
def researches_by_department(request):
    response = {"researches": []}
    request_data = json.loads(request.body)
    department_pk = int(request_data["department"])
    if department_pk != -1:
        if department_pk == -2:
            q = DResearches.objects.filter(is_doc_refferal=True).order_by("title")
        else:
            q = DResearches.objects.filter(podrazdeleniye__pk=department_pk).order_by("title")

        for research in q:
            response["researches"].append({
                "pk": research.pk,
                "title": research.title,
                "short_title": research.short_title,
                "preparation": research.preparation,
                "hide": research.hide,
                "code": research.code,
            })
    return JsonResponse(response)


@login_required
def researches_params(request):
    response = {"researches": []}
    request_data = json.loads(request.body)
    pks = request_data.get("pks", [])
    for research in DResearches.objects.filter(pk__in=pks):
        params = []
        if research.is_paraclinic or research.is_doc_refferal:
            for g in ParaclinicInputGroups.objects.filter(research=research).exclude(title="").order_by("order"):
                params.append({"pk": g.pk, "title": g.title})
        else:
            for f in Fractions.objects.filter(research=research).order_by("sort_weight"):
                params.append({"pk": f.pk, "title": f.title})
        response["researches"].append({"pk": research.pk, "title": research.title,
                                       "short_title": research.get_title(),
                                       "params": params, "is_paraclinic": research.is_paraclinic,
                                       "selected_params": []})
    return JsonResponse(response)


@login_required
@group_required("Оператор", "Конструктор: Параклинические (описательные) исследования")
def researches_update(request):
    response = {"ok": False}
    request_data = json.loads(request.body)
    pk = request_data.get("pk", -2)
    if pk > -2:
        department_pk = request_data.get("department")
        title = request_data.get("title").strip()
        short_title = request_data.get("short_title").strip()
        code = request_data.get("code").strip()
        info = request_data.get("info").strip()
        hide = request_data.get("hide")
        groups = request_data.get("groups")
        if len(title) > 0 and (department_pk == -2 or Podrazdeleniya.objects.filter(pk=department_pk).exists()):
            department = None if department_pk == -2 else Podrazdeleniya.objects.filter(pk=department_pk)[0]
            res = None
            if pk == -1:
                res = DResearches(title=title, short_title=short_title, podrazdeleniye=department, code=code,
                                  is_paraclinic=department_pk != -2 and department.p_type == 3,
                                  paraclinic_info=info, hide=hide, is_doc_refferal=department_pk == -2)
            elif DResearches.objects.filter(pk=pk).exists():
                res = DResearches.objects.filter(pk=pk)[0]
                res.title = title
                res.short_title = short_title
                res.podrazdeleniye = department
                res.code = code
                res.is_paraclinic = department_pk != -2 and department.p_type == 3
                res.is_doc_refferal = department_pk == -2
                res.paraclinic_info = info
                res.hide = hide
            if res:
                res.save()
                templat_obj = ParaclinicTemplateName.make_default(res)
                for group in groups:
                    g = None
                    pk = group["pk"]
                    if pk == -1:
                        g = ParaclinicInputGroups(title=group["title"],
                                                  show_title=group["show_title"],
                                                  research=res,
                                                  order=group["order"],
                                                  hide=group["hide"])
                    elif ParaclinicInputGroups.objects.filter(pk=pk).exists():
                        g = ParaclinicInputGroups.objects.get(pk=pk)
                        g.title = group["title"]
                        g.show_title = group["show_title"]
                        g.research = res
                        g.order = group["order"]
                        g.hide = group["hide"]
                    if g:
                        g.save()
                        for field in group["fields"]:
                            f = None
                            pk = field["pk"]
                            if pk == -1:
                                f = ParaclinicInputField(title=field["title"],
                                                         group=g,
                                                         order=field["order"],
                                                         lines=field["lines"],
                                                         hide=field["hide"],
                                                         default_value=field["default"],
                                                         input_templates=json.dumps(field["values_to_input"]),
                                                         field_type=field.get("field_type", 0),
                                                         required=field.get("required", False))
                            elif ParaclinicInputField.objects.filter(pk=pk).exists():
                                f = ParaclinicInputField.objects.get(pk=pk)
                                f.title = field["title"]
                                f.group = g
                                f.order = field["order"]
                                f.lines = field["lines"]
                                f.hide = field["hide"]
                                f.default_value = field["default"]
                                f.input_templates = json.dumps(field["values_to_input"])
                                f.field_type = field.get("field_type", 0)
                                f.required = field.get("required", False)
                                f.for_talon = field.get("for_talon", False)
                            if f:
                                f.save()

                            if f.default_value == '':
                                continue
                            ParaclinicTemplateField.objects.filter(template_name=templat_obj,
                                                                   input_field=f).update(value=f.default_value)

                response["ok"] = True
        Log(key=pk, type=10000, body=json.dumps(request_data), user=request.user.doctorprofile).save()
    return JsonResponse(response)


@login_required
@group_required("Оператор", "Конструктор: Параклинические (описательные) исследования")
def researches_details(request):
    response = {"pk": -1, "department": -1, "title": '', "short_title": '', "code": '', "info": '', "hide": False,
                "groups": []}
    request_data = json.loads(request.body)
    pk = request_data.get("pk")
    if DResearches.objects.filter(pk=pk).exists():
        res = DResearches.objects.filter(pk=pk)[0]
        response["pk"] = res.pk
        response["department"] = -2 if not res.podrazdeleniye else res.podrazdeleniye.pk
        response["title"] = res.title
        response["short_title"] = res.short_title
        response["code"] = res.code
        response["info"] = res.paraclinic_info or ""
        response["hide"] = res.hide
        for group in ParaclinicInputGroups.objects.filter(research__pk=pk).order_by("order"):
            g = {"pk": group.pk, "order": group.order, "title": group.title, "show_title": group.show_title,
                 "hide": group.hide, "fields": []}
            for field in ParaclinicInputField.objects.filter(group=group).order_by("order"):
                g["fields"].append({
                    "pk": field.pk,
                    "order": field.order,
                    "lines": field.lines,
                    "title": field.title,
                    "default": field.default_value,
                    "hide": field.hide,
                    "values_to_input": json.loads(field.input_templates),
                    "field_type": field.field_type,
                    "required": field.required,
                    "for_talon": field.for_talon,
                    "new_value": ""
                })
            response["groups"].append(g)
    return JsonResponse(response)


@login_required
@group_required("Оператор", "Конструктор: Параклинические (описательные) исследования")
def paraclinic_details(request):
    response = {"groups": []}
    request_data = json.loads(request.body)
    pk = request_data.get("pk")
    for group in ParaclinicInputGroups.objects.filter(research__pk=pk).order_by("order"):
        g = {"pk": group.pk, "order": group.order, "title": group.title, "show_title": group.show_title,
             "hide": group.hide, "fields": []}
        for field in ParaclinicInputField.objects.filter(group=group).order_by("order"):
            g["fields"].append({
                "pk": field.pk,
                "order": field.order,
                "lines": field.lines,
                "title": field.title,
                "default": field.default_value,
                "hide": field.hide,
                "values_to_input": json.loads(field.input_templates),
                "field_type": field.field_type,
                "required": field.required,
                "for_talon": field.for_talon,
            })
        response["groups"].append(g)
    return JsonResponse(response)


def fast_templates(request):
    data = []
    request_data = json.loads(request.body)
    is_all = request_data.get('all', False)

    ParaclinicTemplateName.make_default(DResearches.objects.get(pk=request_data["pk"]))

    rts = ParaclinicTemplateName.objects.filter(research__pk=request_data["pk"])

    if not is_all:
        rts = rts.filter(hide=False)

    for rt in rts.order_by('pk'):
        data.append({
            "pk": rt.pk,
            "title": rt.title,
            "hide": rt.hide,
            "readonly": not is_all or rt.title == ParaclinicTemplateName.DEFAULT_TEMPLATE_TITLE,
        })

    return JsonResponse({"data": data})


def fast_template_data(request):
    request_data = json.loads(request.body)
    p = ParaclinicTemplateName.objects.get(pk=request_data["pk"])
    data = {
        "readonly": p.title == ParaclinicTemplateName.DEFAULT_TEMPLATE_TITLE,
        "hide": p.hide,
        "title": p.title,
        "fields": {},
    }

    for pi in ParaclinicTemplateField.objects.filter(template_name=p).order_by('pk'):
        data["fields"][pi.input_field.pk] = pi.value

    return JsonResponse({"data": data})


@login_required
@group_required("Оператор", "Конструктор: Параклинические (описательные) исследования")
def fast_template_save(request):
    request_data = json.loads(request.body)
    data = request_data["data"]
    if request_data["pk"] == -1:
        p = ParaclinicTemplateName(research=DResearches.objects.get(pk=request_data["research_pk"]),
                                   title=data["title"],
                                   hide=data["hide"])
        p.save()
    else:
        p = ParaclinicTemplateName.objects.get(pk=request_data["pk"])
        p.title = data["title"]
        p.hide = data["hide"]
        p.save()
    to_delete = []
    has = []
    for pi in ParaclinicTemplateField.objects.filter(template_name=p):
        if str(pi.input_field.pk) not in data["fields"]:
            to_delete.append(pi.pk)
            has.append(pi.input_field.pk)
        elif data["fields"][str(pi.input_field.pk)] != pi.value:
            pi.value = data["fields"][str(pi.input_field.pk)]
            pi.save()
            has.append(pi.input_field.pk)
        if data["fields"][str(pi.input_field.pk)] == pi.value:
            has.append(pi.input_field.pk)
    ParaclinicTemplateField.objects.filter(pk__in=to_delete).delete()
    for pk in data["fields"]:
        pki = int(pk)
        if pki not in has:
            i = ParaclinicInputField.objects.get(pk=pki)
            if i.field_type in [0, 2]:
                ParaclinicTemplateField(template_name=p, input_field=i, value=data["fields"][pk]).save()
    return JsonResponse({"pk": p.pk})