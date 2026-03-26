# Flowify Spring Boot 설계 명세서

> 작성일: 2026-03-22
> 기반 문서: 요구사항 명세서, SPRING_BOOT_DESIGN.md, DEVELOPMENT_PLAN.md
> 참조 양식: Experfolio 설계 명세서 (design_ref.pdf)

---

## 목차

| 번호 | 파일 | 내용 |
|------|------|------|
| 1 | [1_overview.md](1_overview.md) | 개요 - 시스템 목표, 주요 기능, 설계상 제약사항 |
| 2 | [2_database_design.md](2_database_design.md) | 데이터베이스 설계 - MongoDB 컬렉션, 스키마, 인덱스 |
| 3 | [3_deployment_diagram.md](3_deployment_diagram.md) | 객체지향설계 - Deployment Diagram (시스템 운용도) |
| 4 | [4_class_diagram.md](4_class_diagram.md) | 객체지향설계 - Class Diagram (서브시스템별 클래스 다이어그램) |
| 5 | [5_sequence_diagram.md](5_sequence_diagram.md) | 객체지향설계 - Sequence Diagram (유스케이스별 시퀀스 다이어그램) |
| 6 | [6_design_classes.md](6_design_classes.md) | 객체지향설계 - Design Classes (클래스별 속성/메소드 상세 명세) |
| 7 | [7_requirements_traceability.md](7_requirements_traceability.md) | 요구분석 참조표 |

---

## 설계 범위

본 설계 명세서는 **Flowify Spring Boot 메인 백엔드**에 해당하는 부분만을 다룬다.

**포함:**
- 시스템 개요 및 설계 제약사항
- MongoDB 데이터베이스 설계
- 전체 시스템 배포 다이어그램
- Spring Boot 서브시스템별 클래스 다이어그램
- Spring Boot가 관여하는 유스케이스별 시퀀스 다이어그램
- 각 클래스의 속성/메소드 상세 명세
- 요구분석 참조표

**제외:**
- 사용자 인터페이스 설계 (프론트엔드 담당)
- FastAPI 내부 설계 (별도 레포)

---

## 관련 문서

| 문서 | 위치 |
|------|------|
| 요구사항 명세서 | [../requirements/](../requirements/) |
| 프로젝트 분석 문서 | [../PROJECT_ANALYSIS.md](../PROJECT_ANALYSIS.md) |
| Spring Boot 설계 문서 | [../SPRING_BOOT_DESIGN.md](../SPRING_BOOT_DESIGN.md) |
| 개발 계획서 | [../DEVELOPMENT_PLAN.md](../DEVELOPMENT_PLAN.md) |
