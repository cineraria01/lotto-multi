import base64
import random
import traceback
from io import BytesIO

from PIL import Image
from support import SupportDiscord
from tool import ToolNotify

from .ff_pylotto import DhLottery
from .model import ModelLottoItem
from .setup import *


class ModuleBasic(PluginModuleBase):
    
    def __init__(self, P):
        super(ModuleBasic, self).__init__(P, name='basic', first_menu='setting', scheduler_desc="로또 자동 구입")
        self.db_default = {
            f'db_version': '1',
            f'{self.name}_auto_start': 'False',
            f'{self.name}_interval': '0 8 * * *',
            f'{self.name}_db_delete_day': '30',
            f'{self.name}_db_auto_delete': 'False',
            f'{P.package_name}_item_last_list_option': '',

            f'driver_mode': 'remote',
            f'driver_local_headless': 'False',
            f'driver_remote_url': 'http://172.17.0.1:4422/wd/hub',
            f'accounts': '[]',  # JSON array of {id, passwd, alias}
            f'charge_money': '20000',
            f'buy_data': '',
            f'notify_mode': 'always',
            f'buy_mode_one_of_week': 'True',
        }
        self.web_list_model = ModelLottoItem

    def process_menu(self, sub, req):
        arg = P.ModelSetting.to_dict()
        if sub == 'setting':
            arg['is_include'] = F.scheduler.is_include(self.get_scheduler_name())
            arg['is_running'] = F.scheduler.is_running(self.get_scheduler_name())
        return render_template(f'{P.package_name}_{self.name}_{sub}.html', arg=arg)
    
    def process_command(self, command, arg1, arg2, arg3, req):
        ret = {'ret': 'success'}
        if command == 'test_info' or command == 'test_buy':
            results = self.do_action_multi(mode=command)
            
            if len(results) == 0:
                ret['modal'] = "등록된 계정이 없습니다."
                ret['title'] = '에러'
            else:
                modal_text = f"전체 계정: {len(results)}개\n"
                modal_text += "=" * 30 + "\n"
                
                for idx, data in enumerate(results):
                    modal_text += f"\n[계정 {idx+1}: {data.get('account_alias', data.get('account_id', '알수없음'))}]\n"
                    
                    if data['status'] == 'LOGIN_FAILED':
                        modal_text += "로그인 실패\n"
                    elif data['status'] == 'error':
                        modal_text += f"에러: {data.get('error', '알수없는 에러')}\n"
                    else:
                        if 'deposit' in data:
                            modal_text += f"예치금: {data['deposit']:,}원\n"
                        if 'history' in data:
                            modal_text += f"이미 구입: {data['history']['count']}건 (미추첨)\n"
                        if 'available_count' in data:
                            modal_text += f"구매 가능: {data['available_count']}건\n"
                        if 'buy' in data:
                            modal_text += f"회차: {data['buy']['round']}\n"
                            modal_text += f"구매: {len(data['buy']['buy_list'])}건\n"
                        
                        if data['status'] == 'NOT_AVAILABLE_COUNT':
                            modal_text += "상태: 구매 가능 건수 없음\n"
                        elif data['status'] == 'ALREADY_THIS_WEEK_BUY':
                            modal_text += "상태: 이번 주 이미 구매\n"
                        elif data['status'] == 'NOT_AVAILABLE_MONEY':
                            modal_text += "상태: 예치금 부족\n"
                    
                    modal_text += "-" * 20 + "\n"
                
                ret['modal'] = modal_text
                ret['title'] = "멀티 계정 테스트"
                ret['data'] = results
        elif command == 'save_accounts':
            # 계정 정보 저장 명령어
            import json
            accounts = json.loads(arg1)
            P.ModelSetting.set('accounts', json.dumps(accounts))
            ret['msg'] = f"{len(accounts)}개 계정이 저장되었습니다."
        return jsonify(ret)

    def scheduler_function(self):
        try:
            noti_mode = P.ModelSetting.get('notify_mode')
            results = self.do_action_multi()  # 멀티 계정 처리
            
            # 전체 결과 집계
            total_bought = 0
            total_accounts = len(results)
            success_accounts = 0
            failed_accounts = []
            messages = []
            
            for result in results:
                if result['status'] == 'success':
                    success_accounts += 1
                    if 'buy' in result and len(result['buy']['buy_list']) > 0:
                        total_bought += len(result['buy']['buy_list'])
                        # 각 계정별 구매 내역 DB 저장
                        db_item = ModelLottoItem()
                        db_item.round = result['buy']['round']
                        db_item.count = len(result['buy']['buy_list'])
                        db_item.account_alias = result['account_alias']
                        db_item.data = result
                        if 'buy' in result:
                            img_bytes = base64.b64decode(result['buy']['screen_shot'])
                            filepath = os.path.join(F.config['path_data'], 'tmp', f"proxy_{result['account_alias']}_{str(time.time())}.png")
                            img = Image.open(BytesIO(img_bytes))
                            img.save(filepath)
                            img_url = SupportDiscord.discord_proxy_image_localfile(filepath)
                            db_item.img = img_url
                        db_item.save()
                else:
                    failed_accounts.append(result['account_alias'])
                
                # 계정별 상태 메시지
                account_msg = f"\n[{result['account_alias']}]"
                if 'deposit' in result:
                    account_msg += f" 예치금: {result['deposit']:,}원"
                if 'available_count' in result:
                    account_msg += f" 구매가능: {result['available_count']}건"
                if result['status'] == 'NOT_AVAILABLE_COUNT':
                    account_msg += " (구매가능 건수 없음)"
                elif result['status'] == 'ALREADY_THIS_WEEK_BUY':
                    account_msg += " (이번주 이미 구매)"
                elif result['status'] == 'NOT_AVAILABLE_MONEY':
                    account_msg += " (예치금 부족)"
                elif result['status'] == 'LOGIN_FAILED':
                    account_msg += " (로그인 실패)"
                elif 'buy' in result:
                    account_msg += f" 구매: {len(result['buy']['buy_list'])}건"
                messages.append(account_msg)
            
            # 전체 알림 메시지 구성
            msg = f'로또 멀티 구매 완료\n'
            msg += f'전체 계정: {total_accounts}개 (성공: {success_accounts}, 실패: {len(failed_accounts)})\n'
            msg += f'총 구매: {total_bought}건'
            msg += ''.join(messages)
            
            if failed_accounts:
                msg += f'\n\n실패 계정: {", ".join(failed_accounts)}'
            
            # 알림 발송 조건
            notify = False
            if noti_mode == 'always':
                notify = True
            elif noti_mode == 'real_buy' and total_bought > 0:
                notify = True
            elif noti_mode == 'real_buy' and any(r['status'] == 'NOT_AVAILABLE_MONEY' for r in results):
                notify = True
                
            if notify:
                # 첫 번째 성공한 구매의 스크린샷을 대표 이미지로 사용
                img_url = None
                for result in results:
                    if 'buy' in result and len(result['buy']['buy_list']) > 0:
                        img_bytes = base64.b64decode(result['buy']['screen_shot'])
                        filepath = os.path.join(F.config['path_data'], 'tmp', f"proxy_summary_{str(time.time())}.png")
                        img = Image.open(BytesIO(img_bytes))
                        img.save(filepath)
                        img_url = SupportDiscord.discord_proxy_image_localfile(filepath)
                        break
                        
                ToolNotify.send_message(msg, 'lotto-multi', image_url=img_url)
                
        except Exception as e:
            P.logger.error(f'Exception:{str(e)}')
            P.logger.error(traceback.format_exc())

    def do_action_multi(self, mode="buy", max_retries=2):
        """여러 계정을 순차적으로 처리"""
        import json
        import time
        results = []
        accounts_str = P.ModelSetting.get('accounts') or '[]'
        P.logger.info(f"Raw accounts string from settings: {accounts_str}")
        
        try:
            accounts = json.loads(accounts_str)
        except json.JSONDecodeError as e:
            P.logger.error(f"Failed to parse accounts JSON: {e}")
            accounts = []
        
        P.logger.info(f"Loaded accounts: {len(accounts)} accounts")
        
        if not accounts:
            # 이전 버전 호환성을 위해 단일 계정 확인
            old_id = P.ModelSetting.get('user_id', '')
            old_pw = P.ModelSetting.get('user_passwd', '')
            if old_id and old_pw:
                accounts = [{'id': old_id, 'passwd': old_pw, 'alias': '기본'}]
        
        for idx, account in enumerate(accounts):
            retry_count = 0
            while retry_count <= max_retries:
                try:
                    P.logger.info(f"Processing account {idx+1}/{len(accounts)}: {account.get('alias', account['id'])} (시도: {retry_count+1})")
                    result = self.do_action_single(account, mode)
                    result['account_alias'] = account.get('alias', account['id'])
                    result['account_id'] = account['id']
                    
                    # 로그인 실패나 에러가 아닌 경우 성공으로 처리
                    if result['status'] not in ['LOGIN_FAILED', 'error']:
                        results.append(result)
                        break
                    elif retry_count < max_retries:
                        P.logger.warning(f"Retrying account {account.get('alias', account['id'])} after failure...")
                        time.sleep(random.randint(5, 10))  # 재시도 전 대기
                        retry_count += 1
                    else:
                        # 최대 재시도 횟수 도달
                        result['retry_count'] = retry_count
                        results.append(result)
                        break
                        
                except Exception as e:
                    P.logger.error(f"Error processing account {account.get('alias', account['id'])}: {str(e)}")
                    if retry_count < max_retries:
                        retry_count += 1
                        time.sleep(random.randint(5, 10))
                    else:
                        results.append({
                            'status': 'error',
                            'account_alias': account.get('alias', account['id']),
                            'account_id': account['id'],
                            'error': str(e),
                            'retry_count': retry_count
                        })
                        break
            
            # 계정 간 대기 시간 (봇 방지)
            if idx < len(accounts) - 1:
                time.sleep(random.randint(3, 7))
                
        return results

    def do_action_single(self, account, mode="buy"):
        """단일 계정 처리"""
        try:
            ret = {'status': None}
            lotto = DhLottery(P)
            lotto.driver_init(P.ModelSetting.get('driver_mode'), P.ModelSetting.get_bool('driver_local_headless'), P.ModelSetting.get('driver_remote_url'))
            
            # 로그인
            try:
                P.logger.debug(f"Attempting login for account: {account.get('id', 'NO_ID')}")
                lotto.login(account['id'], account['passwd'])
                P.logger.info(f"Login successful for account: {account.get('id')}")
            except Exception as e:
                P.logger.error(f"Login failed for {account['id']}: {str(e)}")
                ret['status'] = 'LOGIN_FAILED'
                ret['error'] = str(e)
                return ret
            
            try:    
                P.logger.debug("Checking deposit...")
                ret['deposit'] = lotto.check_deposit()
                P.logger.debug(f"Deposit: {ret['deposit']}")
                
                P.logger.debug("Checking history...")
                ret['history'] = lotto.check_history()
                P.logger.debug(f"History count: {ret['history']['count']}")
            except Exception as e:
                P.logger.error(f"Error during deposit/history check: {str(e)}")
                P.logger.error(traceback.format_exc())
                raise
                
            stream = BytesIO(ret['history']['screen_shot'])
            img = Image.open(stream)
            img.save(stream, format='png')
            ret['history']['screen_shot'] = base64.b64encode(stream.getvalue()).decode() 
            ret['available_count'] = 5 - ret['history']['count']
            
            if mode == 'test_info':
                ret['status'] = 'success'
                return ret
            
            buy_data = self.get_buy_data()
            if ret['available_count'] == 0:
                ret['status'] = 'NOT_AVAILABLE_COUNT'
            elif P.ModelSetting.get_bool('buy_mode_one_of_week') and ret['available_count'] != 5:
                ret['status'] = 'ALREADY_THIS_WEEK_BUY'
            else:
                if min(len(buy_data), ret['available_count']) * 1000 > ret['deposit']:
                    ret['status'] = 'NOT_AVAILABLE_MONEY'

            if len(buy_data) > ret['available_count']:
                buy_data = buy_data[:ret['available_count']]

            if ret['status'] is None:
                if mode == 'test_buy':
                    ret['buy'] = lotto.buy_lotto(buy_data, dry=True)
                else:
                    ret['buy'] = lotto.buy_lotto(buy_data)
                stream = BytesIO(ret['buy']['screen_shot'])
                img = Image.open(stream)
                img.save(stream, format='png')
                ret['buy']['screen_shot'] = base64.b64encode(stream.getvalue()).decode()
                ret['status'] = 'success'
            elif ret['status'] in ['NOT_AVAILABLE_COUNT', 'ALREADY_THIS_WEEK_BUY', 'NOT_AVAILABLE_MONEY']:
                # 구매하지 않았지만 정상 상태
                ret['status'] = 'success'
                
            return ret
        except Exception as e:
            P.logger.error(f'Exception:{str(e)}')
            P.logger.error(traceback.format_exc())
            ret['status'] = 'error'
            ret['log'] = str(traceback.format_exc())
            return ret
        finally:
            try:
                lotto.driver_quit()
            except:
                pass

    def do_action(self, mode="buy"):
        try:
            ret = {'status': None}
            lotto = DhLottery(P)
            lotto.driver_init(P.ModelSetting.get('driver_mode'), P.ModelSetting.get_bool('driver_local_headless'), P.ModelSetting.get('driver_remote_url'))
            # 멀티 계정 처리를 위해 개별 계정 로그인은 나중에 처리
            # lotto.login(P.ModelSetting.get('user_id'), P.ModelSetting.get('user_passwd'))
            ret['deposit'] = lotto.check_deposit()
            ret['history'] = lotto.check_history()
            stream = BytesIO(ret['history']['screen_shot'])
            img = Image.open(stream)
            img.save(stream, format='png')
            ret['history']['screen_shot'] = base64.b64encode(stream.getvalue()).decode() 
            ret['available_count'] = 5 - ret['history']['count']
            if mode == 'test_info':
                return ret
            
            buy_data = self.get_buy_data()
            if ret['available_count'] == 0:
                ret['status'] = 'NOT_AVAILABLE_COUNT'
            elif P.ModelSetting.get_bool('buy_mode_one_of_week') and ret['available_count'] != 5:
                ret['status'] = 'ALREADY_THIS_WEEK_BUY'
            else:
                if min(len(buy_data), ret['available_count']) * 1000 > ret['deposit']:
                    ret['status'] = 'NOT_AVAILABLE_MONEY'

            if len(buy_data) > ret['available_count']:
                buy_data = buy_data[:ret['available_count']]

            if ret['status'] is None:
                if mode == 'test_buy':
                    ret['buy'] = lotto.buy_lotto(buy_data, dry=True)
                else:
                    ret['buy'] = lotto.buy_lotto(buy_data)
                stream = BytesIO(ret['buy']['screen_shot'])
                img = Image.open(stream)
                img.save(stream, format='png')
                ret['buy']['screen_shot'] = base64.b64encode(stream.getvalue()).decode()
            return ret
        except Exception as e:
            P.logger.error(f'Exception:{str(e)}')
            P.logger.error(traceback.format_exc())
            ret['status'] = 'fail'
            ret['log'] = str(traceback.format_exc())
        finally:
            lotto.driver_quit()
            #P.logger.debug(d(ret))
        return ret

    @staticmethod
    def get_buy_data():
        def auto():
            ret = []
            while len(ret) < 6:
                tmp = str(random.randint(1, 45))
                if tmp not in ret:
                    ret.append(tmp)
            return ret

        data = P.ModelSetting.get_list('buy_data')
        ret = []
        plugin_auto = auto()
        for item in data:
            if item.startswith('plugin_auto'):
                ret.append(f"manual : {','.join(plugin_auto)}")
            else:
                ret.append(item)
        P.logger.info(f"Buy data: {ret}")
        return ret
