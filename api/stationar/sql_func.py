from django.db import connection
from laboratory.settings import TIME_ZONE


def get_research(title_podr, vertical_result_display):
    """
    Возврат: id услуги, title-услуги

    """

    with connection.cursor() as cursor:
        cursor.execute("""WITH
        t_podr AS (
	        SELECT id as podr_id, title as podr_title FROM public.podrazdeleniya_podrazdeleniya),
	    
	    t_research AS (
	        SELECT id as research_id, title as research_title, vertical_result_display, podrazdeleniye_id 
	        FROM public.directory_researches)
	    
	    SELECT research_id, research_title FROM t_research
        LEFT JOIN t_podr
        ON t_research.podrazdeleniye_id=t_podr.podr_id
        WHERE podr_title = %(title_podr)s and vertical_result_display = %(vertical)s
        ORDER BY research_id
        """, params={'title_podr' : title_podr, 'vertical' : vertical_result_display})

        row = cursor.fetchall()
    return row


def get_iss(list_research_id, list_dirs):
    """
    Возврат: id-iss
    добавить:
    """
    with connection.cursor() as cursor:
        cursor.execute("""WITH
        t_iss AS (SELECT id, research_id FROM public.directions_issledovaniya
        WHERE napravleniye_id = ANY(ARRAY[%(num_dirs)s]) AND research_id = ANY(ARRAY[%(id_researches)s]) 
        AND time_confirmation IS NOT NULL) 
        
        SELECT * FROM t_iss
        """, params={'id_researches': list_research_id, 'num_dirs': list_dirs})
        row = cursor.fetchall()
    return row


def get_fraction_horizontal(list_iss):
    """
    возвращает уникальные фракци(id, title, units), которые присутствуют во всех исследованиях
    """
    with connection.cursor() as cursor:
        cursor.execute("""WITH
        t_fraction AS (SELECT id as id_frac, title as title_frac FROM public.directory_fractions ORDER BY id)

        SELECT DISTINCT ON (fraction_id) fraction_id, title_frac, units FROM directions_result
        LEFT JOIN t_fraction ON directions_result.fraction_id = t_fraction.id_frac
        WHERE issledovaniye_id = ANY(ARRAY[%(id_iss)s])
        ORDER by fraction_id
        """, params={'id_iss': list_iss})
        row = cursor.fetchall()
    return row


def get_result_fraction(list_iss):
    """
    возвращает результат: дата, фракция, значение(value)
    """
    with connection.cursor() as cursor:
        cursor.execute("""WITH
        t_fraction AS (SELECT id as id_frac, title as title_frac FROM public.directory_fractions ORDER BY id),
        
        t_iss AS (SELECT id as iss_id, napravleniye_id, to_char(time_confirmation AT TIME ZONE %(tz)s, 'DD.MM.YY') as date_confirm
        FROM public.directions_issledovaniya 
        WHERE id = ANY(ARRAY[%(id_iss)s]) AND time_confirmation IS NOT NULL)

        SELECT fraction_id, issledovaniye_id, title_frac, value, date_confirm, napravleniye_id FROM directions_result
        LEFT JOIN t_fraction ON directions_result.fraction_id = t_fraction.id_frac
        LEFT JOIN t_iss ON directions_result.issledovaniye_id = t_iss.iss_id
        WHERE issledovaniye_id = ANY(ARRAY[%(id_iss)s])
        ORDER by napravleniye_id, date_confirm
        """, params={'id_iss': list_iss, 'tz': TIME_ZONE})
        row = cursor.fetchall()
    return row
