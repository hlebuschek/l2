from django.db import connection
from laboratory.settings import TIME_ZONE
from utils.db import namedtuplefetchall


def last_result_researches_years(client_id, years, researches):
    with connection.cursor() as cursor:
        cursor.execute(
            """
                WITH 
                t_iss AS (
                SELECT
                date_part('year', directions_issledovaniya.time_confirmation) as year_date,
                date_part('month', directions_issledovaniya.time_confirmation) as month_date,
                date_part('day', directions_issledovaniya.time_confirmation) as day_date, 
                directions_issledovaniya.id as iss_id, 
                directions_napravleniya.client_id as card_id, 
                directions_issledovaniya.napravleniye_id as dir_id,
                directions_issledovaniya.research_id as research_id,
                directions_issledovaniya.time_confirmation as confirm
                FROM directions_issledovaniya
                LEFT JOIN directions_napravleniya
                    ON directions_issledovaniya.napravleniye_id =directions_napravleniya.id
                WHERE 
                directions_napravleniya.client_id = 199554 and 
                directions_issledovaniya.research_id = ANY(ARRAY[%(researches)s]) and
                date_part('year', directions_issledovaniya.time_confirmation AT TIME ZONE %(tz)s) = ANY(ARRAY[%(years)s])
                ORDER BY directions_issledovaniya.time_confirmation DESC)
                
                SELECT DISTINCT ON (t_iss.year_date, t_iss.research_id) 
                    t_iss.year_date, t_iss.month_date, t_iss.day_date, t_iss.iss_id, t_iss.card_id, t_iss.dir_id, t_iss.research_id, t_iss.confirm
                From t_iss
                ORDER BY t_iss.year_date DESC, t_iss.research_id DESC, t_iss.confirm DESC 
            """,
            params={'tz': TIME_ZONE, 'card_pk': client_id, 'researches': researches, 'years': years},
        )
        rows = namedtuplefetchall(cursor)
    return rows
