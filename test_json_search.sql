-- 测试JSON搜索的SQL命令
-- 请在Oracle数据库中执行这些命令来帮助调试

-- 1. 检查表中的数据
SELECT COUNT(*) AS total_records FROM MEDICAL_DOCUMENTS;

-- 2. 查看所有记录的基本信息
SELECT patient_id, 
       SUBSTR(DOC_DATA, 1, 100) AS doc_preview,
       created_date
FROM MEDICAL_DOCUMENTS;

-- 3. 测试患者ID匹配
SELECT patient_id, DOC_DATA 
FROM MEDICAL_DOCUMENTS 
WHERE patient_id LIKE '%周某某%';

-- 4. 测试JSON内容搜索（查找"主诉"）
SELECT patient_id, DOC_DATA 
FROM MEDICAL_DOCUMENTS 
WHERE UPPER(DOC_DATA) LIKE UPPER('%主诉%');

-- 5. 测试JSON内容搜索（查找"头晕"）
SELECT patient_id, DOC_DATA 
FROM MEDICAL_DOCUMENTS 
WHERE UPPER(DOC_DATA) LIKE UPPER('%头晕%');

-- 6. 组合条件测试
SELECT patient_id, DOC_DATA 
FROM MEDICAL_DOCUMENTS 
WHERE patient_id LIKE '%周某某%' 
  AND (UPPER(DOC_DATA) LIKE UPPER('%主诉%') OR UPPER(DOC_DATA) LIKE UPPER('%头晕%'));
