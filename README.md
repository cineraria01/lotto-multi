### 로또 구입 (멀티 계정 지원)

honeypig5의 로또 플러그인을 수정하여 여러 계정으로 순차적으로 로또를 구입할 수 있도록 개선한 버전입니다.
기존에는 1개의 계정만 사용 가능했으나, 이제 여러 계정을 등록하여 순차적으로 구입이 가능합니다.

##### 드라이버 로컬
크롬이 설치되어 있어야 함.  
자동 설치 드라이버 위치 : C:\Users\사용자\.wdm  
윈도우(맥) 사용자만 가능하나 윈도우에서도 리모트 환경을 이용할 수 있음.


##### 드라이버 리모트

VPS나 도커는 리모트만 가능.

selenium 공식 도커 이미지중 firefox로 테스트 함.

공식 사이트 : [https://github.com/SeleniumHQ/docker-selenium](https://github.com/SeleniumHQ/docker-selenium)
- amd64  
    ```
    docker run -d --name selenium_firefox -p 4422:4444 -p 5922:5900 -p 7922:7900 --shm-size 2g selenium/standalone-firefox:latest
    ```


- arm (오라클 A1)  
    ```
    docker run -d --name selenium_firefox -p 4422:4444 -p 5922:5900 -p 7922:7900 --shm-size 2g seleniarm/standalone-firefox:latest 
    ```

selenium / seleniarm 차이
7900포트는 noVnc 포트로 웹에서 접속하여 화면을 확인 할 수 있음.  
웹 비밀번호 : secret



구매시 noVnc 스샷


<br><br>

##### 자동 구입정보

  - auto
    자동
  - manual : 2, 3, 4, 8, 45, 3  
    수동 입력
  - manual : 2, 3, 4  
    3개 수동 입력 후 자동
  - plugin_auto
    플러그인에서 자동 번호를 구한 후 입력.   
    동일한 자동 번호를 여러 게임에 넣고 싶을 때.


  전체 예)
  ```
  manual : 8, 28, 12, 9, 10, 33
  #manual : 8, 28, 12, 9
  auto
  plugin_auto
  plugin_auto
  plugin_auto
  ```
  
  plugin_auto 는 랜덤이나 3,4,5 게임 모두 같은 번호.  
  정보안에서 # 주석 가능