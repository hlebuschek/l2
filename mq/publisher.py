from laboratory.settings import RMQ_URL


def mq_send(m_type, m_obj, m_pk, queue='l2_models_events'):
    import pika
    try:
        connection = pika.BlockingConnection(pika.URLParameters(RMQ_URL))
        channel = connection.channel()
        channel.queue_declare(queue=queue)
        channel.basic_publish(exchange='',
                              routing_key='l2_models_events',
                              body="{}|{}|{}".format(m_type, m_obj, m_pk))
        connection.close()
    except Exception as e:
        import logging
        logger = logging.getLogger("pika")
        from traceback import format_exc
        logger.error(format_exc())
