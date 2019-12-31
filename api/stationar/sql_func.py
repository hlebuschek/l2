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
    добавить: AND time_confirmation IS NOT NULL
    """
    with connection.cursor() as cursor:
        cursor.execute("""
        SELECT id, research_id FROM public.directions_issledovaniya
        WHERE napravleniye_id = ANY(ARRAY[%(num_dirs)s]) AND research_id = ANY(ARRAY[%(id_researches)s]) 
        
        """, params={'id_researches': list_research_id, 'num_dirs': list_dirs})
        row = cursor.fetchall()
    return row



