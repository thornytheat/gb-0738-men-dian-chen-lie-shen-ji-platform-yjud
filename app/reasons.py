REASONS = {
    'COLUMN_COUNT': '字段数不符', 'BAD_ID': '编号无效', 'UNKNOWN_STORE': '门店未登记',
    'UNKNOWN_GROUP': '店组未登记', 'UNKNOWN_SLOT': '柜位未登记', 'UNKNOWN_VISIT': '巡检未登记',
    'BAD_ZONE': '时区无效', 'BAD_CLOCK': '日期时间无效', 'AMBIGUOUS_CLOCK': '本地时间有两个对应时刻',
    'NONEXISTENT_CLOCK': '本地时间已跳过', 'OUTSIDE_CAMPAIGN': '不在巡检账期',
    'DUPLICATE_ROW': '相同主键的重复抄录', 'KEY_CONFLICT': '相同主键的记录矛盾',
    'BAD_NUMBER': '整数格式无效', 'BAD_INTERVAL': '陈列图生效区间无效', 'BAD_SKU': '商品编号无效',
    'PLAN_OVERLAP': '同一巡检时刻有多版陈列图', 'PLAN_MISSING': '巡检时刻无生效陈列图',
    'VISIT_MISSING': '柜位所属门店未有效到访', 'BAD_PHOTO_FILE': '照片文件名或内容无效',
    'PHOTO_EXPIRED': '拍摄时间偏离巡检', 'PHOTO_REUSED': '照片字节在不同柜位或巡检复用',
    'PHOTO_ID_CONFLICT': '照片编号绑定冲突', 'PHOTO_UNAVAILABLE': '清点引用的图证不可用',
    'MISSING_PHOTO': '缺有效照片，待补证', 'SCAN_INCOMPLETE': '缺清点完成记录',
    'BAD_OBSERVATION': '清点行格式无效', 'OBSERVATION_CONFLICT': '同商品清点结果矛盾',
    'MISSING_SKU': '应陈商品未出现', 'WRONG_SKU': '出现陈列图外的商品',
    'UNDER_FACINGS': '应陈商品排面不足', 'PRICE_MISMATCH': '标价与陈列图不符',
}


def mark(source, code, **context):
    return {'source': source, 'reason': code, 'label': REASONS[code], **context}
